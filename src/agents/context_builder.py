"""Server Context Builder (MULTI_AGENT_IMPLEMENTATION_PLAN.md #4, architecture diagram: `API ->
Server Context Builder -> Scope and Policy Resolver`).

Turns untrusted client input (AgentInvocationRequest) plus the authenticated actor into the single
trusted, immutable AgentContext every downstream layer (router, tools, prompt) reads from - this is
the ONLY place a raw client field is allowed to influence what ends up in AuthorizationContext.
Nothing here calls the LLM: this is G0 (identity/input) + a call into G1 (scope_resolver) laid out as
one function, matching the plan's "policy bằng code" rule.
"""

import time
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.contracts import (
    ActorContext,
    AgentContext,
    AgentIntent,
    AgentInvocationRequest,
    AgentProfile,
    AgentRequestContext,
    AgentRuntimeContext,
    AuthorizationContext,
    PolicyDecision,
)
from src.agents.policies.scope_resolver import resolve_agent_scope
from src.agents.tools.registry import get_profile_registration
from src.db.models import AgentRun, AgentWorkspaceMembership, User


async def _actor_agent_workspace_ids(db: AsyncSession, user_id: str) -> tuple[str, ...]:
    rows = (
        await db.execute(
            select(AgentWorkspaceMembership.agent_workspace_id).where(
                AgentWorkspaceMembership.user_id == user_id,
                AgentWorkspaceMembership.status == "active",
            )
        )
    ).scalars().all()
    return tuple(rows)


async def build_agent_context(
    db: AsyncSession,
    *,
    user: User,
    organization_workspace_id: str,
    invocation: AgentInvocationRequest,
    intent: AgentIntent,
    agent_profile: AgentProfile,
) -> AgentContext:
    """Build the trusted envelope for one agent turn. Always succeeds - a denial is expressed as
    `authorization.decision == DENY` inside the returned context, not an exception, so callers (and
    G6 audit logging) can record the attempt/denial uniformly. Only structurally invalid input
    (caught by AgentContext's own pydantic validators) raises.
    """

    registration = get_profile_registration(agent_profile)
    resolution = await resolve_agent_scope(
        db,
        user_id=user.id,
        organization_workspace_id=organization_workspace_id,
        agent_profile=agent_profile,
        requested_scope=invocation.requested_scope,
        target_agent_workspace_id=invocation.target_agent_workspace_id,
    )
    agent_workspace_ids = await _actor_agent_workspace_ids(db, user.id)

    return AgentContext(
        trace_id=uuid.uuid4().hex,
        actor=ActorContext(
            user_id=user.id,
            organization_workspace_id=organization_workspace_id,
            business_role=resolution.business_role or _default_business_role(),
            agent_workspace_ids=agent_workspace_ids,
        ),
        request=AgentRequestContext(
            text=invocation.message,
            intent=intent,
            requested_scope=invocation.requested_scope,
            target_agent_workspace_id=invocation.target_agent_workspace_id,
        ),
        authorization=AuthorizationContext(
            decision=resolution.decision,
            reason=resolution.reason,
            allowed_agent_workspace_ids=resolution.allowed_agent_workspace_ids,
            allowed_resource_ids=resolution.allowed_resource_ids,
            consent_scope_hash=resolution.consent_scope_hash,
        ),
        runtime=AgentRuntimeContext(
            agent_profile=agent_profile,
            prompt_version=registration.prompt_version,
        ),
    )


def _default_business_role():
    # A denied resolution never sets business_role (scope_resolver only sets it on ALLOW) - this
    # never surfaces to a prompt or a tool since G1 already denied the request; it exists purely so
    # ActorContext's business_role field (non-optional in the contract) can always be constructed.
    from src.agents.contracts import BusinessRole

    return BusinessRole.MEMBER


class AgentRunRecorder:
    """G6 (audit/monitoring) - records one AgentRun row per turn. A thin context manager so every
    call site (router today, /chat tomorrow) gets consistent latency timing and a guaranteed record
    even on an exception (status="error"), without hand-rolling try/finally at each call site."""

    def __init__(self, db: AsyncSession, context: AgentContext):
        self._db = db
        self._context = context
        self._start = 0.0
        self.model = ""
        self.token_usage = 0

    async def __aenter__(self) -> "AgentRunRecorder":
        self._start = time.monotonic()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        latency_ms = int((time.monotonic() - self._start) * 1000)
        context = self._context
        if context.authorization.decision != PolicyDecision.ALLOW:
            status = "denied"
        elif exc is not None:
            status = "error"
        else:
            status = "success"
        self._db.add(
            AgentRun(
                trace_id=context.trace_id,
                actor_user_id=context.actor.user_id,
                organization_workspace_id=context.actor.organization_workspace_id,
                agent_workspace_id=context.request.target_agent_workspace_id,
                agent_profile=context.runtime.agent_profile.value,
                intent=context.request.intent.value,
                requested_scope=context.request.requested_scope.value,
                policy_decision=context.authorization.decision.value,
                policy_reason=context.authorization.reason.value,
                prompt_version=context.runtime.prompt_version,
                model=self.model,
                status=status,
                latency_ms=latency_ms,
                token_usage=self.token_usage,
            )
        )
        await self._db.commit()
        return False  # never swallow the caller's exception
