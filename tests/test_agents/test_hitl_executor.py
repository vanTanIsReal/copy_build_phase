"""src.agents.hitl_executor.execute_action_proposal - payload hash / actor binding / expiry /
idempotency, independent of any specific specialist agent's side effect."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

import src.db.session as db_session
from src.agents.contracts import ActionProposal, ToolResultStatus, action_payload_hash
from src.agents.hitl_executor import ActionProposalRejectedError, execute_action_proposal
from src.db.models import AgentActionExecution, User


async def _user_id(email: str) -> str:
    async with db_session.async_session_maker() as db:
        return (await db.execute(select(User).where(User.email == email))).scalar_one().id


def _proposal(
    actor_user_id: str,
    *,
    created_offset: timedelta = timedelta(seconds=0),
    expires_in: timedelta = timedelta(minutes=15),
    key: str | None = None,
) -> ActionProposal:
    # created_offset lets a caller construct an already-expired proposal (both created_at and
    # expires_at in the past relative to wall-clock "now", but expires_at still > created_at,
    # which ActionProposal's own validator requires) - simulates a proposal drafted 20 minutes ago
    # whose 15-minute window has since lapsed, rather than an impossible "expires before it's
    # created" object.
    created_at = datetime.now(UTC) + created_offset
    payload = {"title": "Ping team", "due_at": "2026-08-25T00:00:00+00:00"}
    return ActionProposal(
        proposal_id="proposal-1",
        trace_id="trace-1",
        actor_user_id=actor_user_id,
        action="preview_delivery_reminder",
        payload=payload,
        payload_hash=action_payload_hash(payload),
        idempotency_key=key or "idempotency-key-1",
        created_at=created_at,
        expires_at=created_at + expires_in,
    )


@pytest.mark.asyncio
async def test_executes_action_fn_and_records_success(auth_headers):
    alice_id = await _user_id("alice@example.com")
    proposal = _proposal(alice_id)
    calls = []

    async def action_fn():
        calls.append(1)
        return {"reminder_id": "reminder-1"}

    async with db_session.async_session_maker() as db:
        result = await execute_action_proposal(db, proposal=proposal, confirming_user_id=alice_id, action_fn=action_fn)

    assert result.status == ToolResultStatus.SUCCESS
    assert result.payload == {"reminder_id": "reminder-1"}
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_double_confirm_with_same_idempotency_key_does_not_run_action_fn_twice(auth_headers):
    alice_id = await _user_id("alice@example.com")
    proposal = _proposal(alice_id, key="double-click-key")
    calls = []

    async def action_fn():
        calls.append(1)
        return {"reminder_id": f"reminder-{len(calls)}"}

    async with db_session.async_session_maker() as db:
        first = await execute_action_proposal(db, proposal=proposal, confirming_user_id=alice_id, action_fn=action_fn)
    async with db_session.async_session_maker() as db:
        second = await execute_action_proposal(db, proposal=proposal, confirming_user_id=alice_id, action_fn=action_fn)

    assert len(calls) == 1  # action_fn only really ran once
    assert first.payload == second.payload == {"reminder_id": "reminder-1"}


@pytest.mark.asyncio
async def test_rejects_a_proposal_confirmed_by_a_different_user(auth_headers, other_auth_headers):
    alice_id = await _user_id("alice@example.com")
    bob_id = await _user_id("bob@example.com")
    proposal = _proposal(alice_id)

    async def action_fn():
        return {}

    async with db_session.async_session_maker() as db:
        with pytest.raises(ActionProposalRejectedError):
            await execute_action_proposal(db, proposal=proposal, confirming_user_id=bob_id, action_fn=action_fn)


@pytest.mark.asyncio
async def test_rejects_an_expired_proposal(auth_headers):
    alice_id = await _user_id("alice@example.com")
    proposal = _proposal(alice_id, created_offset=timedelta(minutes=-20), expires_in=timedelta(minutes=15))

    async def action_fn():
        return {}

    async with db_session.async_session_maker() as db:
        with pytest.raises(ActionProposalRejectedError):
            await execute_action_proposal(db, proposal=proposal, confirming_user_id=alice_id, action_fn=action_fn)


@pytest.mark.asyncio
async def test_a_failing_action_fn_is_recorded_and_reraised_not_swallowed(auth_headers):
    alice_id = await _user_id("alice@example.com")
    proposal = _proposal(alice_id, key="failing-key")

    async def action_fn():
        raise RuntimeError("google api down")

    async with db_session.async_session_maker() as db:
        with pytest.raises(RuntimeError, match="google api down"):
            await execute_action_proposal(db, proposal=proposal, confirming_user_id=alice_id, action_fn=action_fn)

    async with db_session.async_session_maker() as db:
        execution = await db.get(AgentActionExecution, "failing-key")
    assert execution is not None
    assert execution.status == "error"
