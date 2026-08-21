"""G2 - Retrieval boundary guard (MULTI_AGENT_IMPLEMENTATION_PLAN.md #5.3 table, row G2 and G1: "Tool
kiểm tra lại scope tại boundary; không tin agent_workspace_id do model truyền").

`AgentContext` is built once per turn and is immutable - but a specialist agent can run several tool
calls in one turn (e.g. `get_delivery_tasks` then `build_delivery_brief`), and membership/consent can
change *during* a long-running turn (a lead is removed from the workspace mid-conversation, a group's
AI policy is toggled off). Every specialist tool MUST call `enforce_agent_resource_access` before
touching a resource - re-checking membership/consent live rather than trusting the context snapshot
from the start of the turn, which is exactly the same "stale HITL" principle
docs/P0_AI_CONSENT_AND_ACTION_SAFETY.md already applies to /chat/resume.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.contracts import AgentContext, PolicyDecision, PolicyReason
from src.agents.policies.scope_resolver import resolve_agent_scope


class AgentResourceDeniedError(PermissionError):
    def __init__(self, reason: PolicyReason):
        super().__init__(reason.value)
        self.reason = reason


async def enforce_agent_resource_access(
    db: AsyncSession,
    *,
    context: AgentContext,
    resource_id: str,
) -> None:
    """Re-evaluate current membership and consent at every specialist tool boundary. Raises
    AgentResourceDeniedError (never returns a value) so a tool that forgets to check the return value
    can't accidentally proceed - the only way past this call is for it to not raise."""

    if context.authorization.decision != PolicyDecision.ALLOW:
        raise AgentResourceDeniedError(context.authorization.reason)

    resolution = await resolve_agent_scope(
        db,
        user_id=context.actor.user_id,
        organization_workspace_id=context.actor.organization_workspace_id,
        agent_profile=context.runtime.agent_profile,
        requested_scope=context.request.requested_scope,
        target_agent_workspace_id=context.request.target_agent_workspace_id,
    )
    if resolution.decision != PolicyDecision.ALLOW:
        raise AgentResourceDeniedError(resolution.reason)
    if resolution.consent_scope_hash != context.authorization.consent_scope_hash:
        raise AgentResourceDeniedError(PolicyReason.CONSENT_CHANGED)
    if resource_id not in resolution.allowed_resource_ids:
        raise AgentResourceDeniedError(PolicyReason.RESOURCE_NOT_ALLOWED)


async def enforce_agent_workspace_access(
    db: AsyncSession,
    *,
    context: AgentContext,
    agent_workspace_id: str,
) -> None:
    """Same live re-check as enforce_agent_resource_access, but for tools that read/write
    workspace-scoped records (Task rows, member lists) rather than a specific conversation - the
    thing being authorized is "is this agent_workspace_id still one I'm allowed into", not "is this
    one resource_id in my allowed set". Every Delivery/Quality tool must call this (with the
    workspace id it's about to query) before touching src.db.models.Task or membership rows."""

    if context.authorization.decision != PolicyDecision.ALLOW:
        raise AgentResourceDeniedError(context.authorization.reason)
    if agent_workspace_id != context.request.target_agent_workspace_id:
        # A tool must only ever act on the single workspace this turn's context/route was built
        # for - never a different id it happens to receive as a plain argument.
        raise AgentResourceDeniedError(PolicyReason.WRONG_WORKSPACE)

    resolution = await resolve_agent_scope(
        db,
        user_id=context.actor.user_id,
        organization_workspace_id=context.actor.organization_workspace_id,
        agent_profile=context.runtime.agent_profile,
        requested_scope=context.request.requested_scope,
        target_agent_workspace_id=context.request.target_agent_workspace_id,
    )
    if resolution.decision != PolicyDecision.ALLOW:
        raise AgentResourceDeniedError(resolution.reason)
    if agent_workspace_id not in resolution.allowed_agent_workspace_ids:
        raise AgentResourceDeniedError(PolicyReason.WRONG_WORKSPACE)
