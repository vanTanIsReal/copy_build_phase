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
    """Re-evaluate current membership and consent at every specialist tool boundary."""

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
