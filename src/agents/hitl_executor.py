"""Shared HITL Executor (MULTI_AGENT_IMPLEMENTATION_PLAN.md #9, G5 in the guardrail table): the
one place any specialist agent's confirmed ActionProposal actually runs. Every propose_* tool
(delivery_tool.py, quality_tool.py, and executive_tool.py's propose_executive_meeting) only ever
drafts a proposal - nothing calls a real side effect (create a Reminder, a Calendar event, ...)
except through `execute_action_proposal` below, after a human has confirmed.

Checks, in order (payload hash, expiry, idempotency - MULTI_AGENT_IMPLEMENTATION_PLAN.md #4 "Shared
HITL Executor" hard requirement):
1. The proposal is still internally consistent (`payload_hash` matches `payload`) - re-validated
   here defensively even though ActionProposal's own pydantic validator already enforces this at
   construction, in case a proposal was round-tripped through client-editable state.
2. `actor_user_id` on the proposal matches the confirming user - a confirm from a different
   session/user than the one the proposal was drafted for is rejected, not silently honoured.
3. Not expired (`ActionProposal.is_expired()`).
4. Idempotency: if `idempotency_key` was already executed (src.db.models.AgentActionExecution),
   return the stored result instead of running the side effect again - a double-click or a retried
   confirm after a dropped response must not create two reminders/meetings.

Only after all four pass does `action_fn` (the real side effect - e.g.
`reminder_service.create_reminder`) actually run.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.contracts import ActionProposal, ToolResult, ToolResultStatus, action_payload_hash
from src.db.models import AgentActionExecution


class ActionProposalRejectedError(PermissionError):
    """Raised for every HITL check failure - callers should surface this as a clear "cannot
    execute this action" response, never as a generic 500."""


async def execute_action_proposal(
    db: AsyncSession,
    *,
    proposal: ActionProposal,
    confirming_user_id: str,
    action_fn: Callable[[], Awaitable[dict]],
) -> ToolResult:
    if proposal.payload_hash != action_payload_hash(proposal.payload):
        raise ActionProposalRejectedError("Proposal payload does not match its hash - reject, do not execute.")
    if proposal.actor_user_id != confirming_user_id:
        raise ActionProposalRejectedError("This proposal was not drafted for the confirming user.")
    if proposal.is_expired(at=datetime.now(UTC)):
        raise ActionProposalRejectedError("Proposal has expired - ask the agent to draft a new one.")

    existing = await db.get(AgentActionExecution, proposal.idempotency_key)
    if existing is not None:
        return ToolResult(
            status=ToolResultStatus.SUCCESS if existing.status == "success" else ToolResultStatus.ERROR,
            payload=existing.result_json,
            error_code=None if existing.status == "success" else "ACTION_PREVIOUSLY_FAILED",
        )

    try:
        result_payload = await action_fn()
    except Exception as exc:
        db.add(
            AgentActionExecution(
                idempotency_key=proposal.idempotency_key,
                proposal_id=proposal.proposal_id,
                trace_id=proposal.trace_id,
                actor_user_id=proposal.actor_user_id,
                action=proposal.action,
                status="error",
                result_json={"error": str(exc)},
            )
        )
        await db.commit()
        raise

    db.add(
        AgentActionExecution(
            idempotency_key=proposal.idempotency_key,
            proposal_id=proposal.proposal_id,
            trace_id=proposal.trace_id,
            actor_user_id=proposal.actor_user_id,
            action=proposal.action,
            status="success",
            result_json=result_payload,
        )
    )
    await db.commit()
    return ToolResult(status=ToolResultStatus.SUCCESS, payload=result_payload)
