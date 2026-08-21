"""G6 audit alerts for the multi-agent workspace feature (Sprint 3) - denial-spike and
workspace_brief_stale, reusing the exact broadcast_to_users pattern usage_service's budget alert
already uses (see tests/test_services/test_usage_service.py for the sibling tests this mirrors)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

import src.db.session as db_session
from src.db.models import AgentRun, User, Workspace
from src.services import agent_audit_service

_ORG_ID = "audit-test-org"


async def _user_id(email: str) -> str:
    async with db_session.async_session_maker() as db:
        return (await db.execute(select(User).where(User.email == email))).scalar_one().id


async def _seed_org() -> None:
    async with db_session.async_session_maker() as db:
        if await db.get(Workspace, _ORG_ID) is None:
            db.add(Workspace(id=_ORG_ID, type="organization", name="Audit Test Org"))
            await db.commit()


async def _add_denied_run(actor_id: str, *, minutes_ago: float = 0) -> None:
    async with db_session.async_session_maker() as db:
        db.add(
            AgentRun(
                trace_id=f"trace-{minutes_ago}-{actor_id}",
                actor_user_id=actor_id,
                organization_workspace_id=_ORG_ID,
                agent_profile="product_delivery",
                intent="delivery_brief",
                requested_scope="workspace",
                policy_decision="DENY",
                policy_reason="DENY_NOT_MEMBER",
                prompt_version="product-delivery-v1",
                status="denied",
                created_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
            )
        )
        await db.commit()


@pytest.mark.asyncio
async def test_denial_spike_fires_exactly_at_threshold(client, auth_headers, admin_auth_headers, monkeypatch):
    await _seed_org()
    alice_id = await _user_id("alice@example.com")
    broadcast = AsyncMock()
    monkeypatch.setattr(agent_audit_service.manager, "broadcast_to_users", broadcast)

    async with db_session.async_session_maker() as db:
        for i in range(4):
            await _add_denied_run(alice_id)
            await agent_audit_service.maybe_alert_denial_spike(db, actor_user_id=alice_id, organization_workspace_id=_ORG_ID)
    broadcast.assert_not_awaited()

    async with db_session.async_session_maker() as db:
        await _add_denied_run(alice_id)
        await agent_audit_service.maybe_alert_denial_spike(db, actor_user_id=alice_id, organization_workspace_id=_ORG_ID)

    broadcast.assert_awaited_once()
    admin_ids, payload = broadcast.call_args.args
    me = await client.get("/api/v1/auth/me", headers=admin_auth_headers)
    assert me.json()["id"] in admin_ids
    assert payload["type"] == "agent_denial_spike"
    assert payload["denied_count"] == 5


@pytest.mark.asyncio
async def test_denial_spike_does_not_refire_past_threshold(auth_headers, admin_auth_headers, monkeypatch):
    """5 denials fires once; a 6th denial (still within the window) must not fire a second alert -
    edge-triggered, same as usage_service's budget alert."""
    await _seed_org()
    alice_id = await _user_id("alice@example.com")
    broadcast = AsyncMock()
    monkeypatch.setattr(agent_audit_service.manager, "broadcast_to_users", broadcast)

    async with db_session.async_session_maker() as db:
        for _ in range(5):
            await _add_denied_run(alice_id)
            await agent_audit_service.maybe_alert_denial_spike(db, actor_user_id=alice_id, organization_workspace_id=_ORG_ID)
    broadcast.assert_awaited_once()
    broadcast.reset_mock()

    async with db_session.async_session_maker() as db:
        await _add_denied_run(alice_id)
        await agent_audit_service.maybe_alert_denial_spike(db, actor_user_id=alice_id, organization_workspace_id=_ORG_ID)
    broadcast.assert_not_awaited()


@pytest.mark.asyncio
async def test_denial_spike_ignores_denials_outside_the_window(auth_headers, admin_auth_headers, monkeypatch):
    await _seed_org()
    alice_id = await _user_id("alice@example.com")
    broadcast = AsyncMock()
    monkeypatch.setattr(agent_audit_service.manager, "broadcast_to_users", broadcast)

    async with db_session.async_session_maker() as db:
        for _ in range(4):
            await _add_denied_run(alice_id, minutes_ago=30)  # outside the 10-minute window
        await _add_denied_run(alice_id)  # 1 recent denial
        await agent_audit_service.maybe_alert_denial_spike(db, actor_user_id=alice_id, organization_workspace_id=_ORG_ID)

    broadcast.assert_not_awaited()


@pytest.mark.asyncio
async def test_denial_spike_no_alert_when_no_admin_users(auth_headers, monkeypatch):
    await _seed_org()
    alice_id = await _user_id("alice@example.com")
    broadcast = AsyncMock()
    monkeypatch.setattr(agent_audit_service.manager, "broadcast_to_users", broadcast)

    async with db_session.async_session_maker() as db:
        for _ in range(5):
            await _add_denied_run(alice_id)
        await agent_audit_service.maybe_alert_denial_spike(db, actor_user_id=alice_id, organization_workspace_id=_ORG_ID)
    broadcast.assert_not_awaited()


@pytest.mark.asyncio
async def test_alert_brief_stale_broadcasts_to_admins(client, admin_auth_headers, monkeypatch):
    await _seed_org()
    broadcast = AsyncMock()
    monkeypatch.setattr(agent_audit_service.manager, "broadcast_to_users", broadcast)

    async with db_session.async_session_maker() as db:
        await agent_audit_service.alert_brief_stale(
            db, agent_workspace_id="aw-1", agent_workspace_name="Product Delivery", brief_type="delivery", organization_workspace_id=_ORG_ID
        )

    broadcast.assert_awaited_once()
    admin_ids, payload = broadcast.call_args.args
    me = await client.get("/api/v1/auth/me", headers=admin_auth_headers)
    assert me.json()["id"] in admin_ids
    assert payload == {
        "type": "workspace_brief_stale",
        "agent_workspace_id": "aw-1",
        "agent_workspace_name": "Product Delivery",
        "brief_type": "delivery",
        "organization_workspace_id": _ORG_ID,
    }
