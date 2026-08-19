"""GET /api/v1/agent-workspaces/{id}/my-membership and ?mine=true.

Only the two self-service, not-yet-user-facing endpoints added on top of the (foundation-only,
not yet wired to /chat) agent-workspace CRUD - see docs/MULTI_AGENT_PROGRESS.md. Fixtures insert
Workspace/AgentWorkspace/AgentWorkspaceMembership rows directly (no admin-CRUD endpoint call
needed to set them up) since none of that is under test here.
"""

import pytest
from sqlalchemy import select

import src.db.session as db_session
from src.db.models import AgentWorkspace, AgentWorkspaceMembership, User, Workspace, WorkspaceMembership


async def _user_id(email: str) -> str:
    async with db_session.async_session_maker() as db:
        return (await db.execute(select(User).where(User.email == email))).scalar_one().id


async def _make_org_and_agent_workspace() -> str:
    """Creates one active organization Workspace with one active AgentWorkspace (product_delivery)
    inside it, with NO members. Returns the agent_workspace_id."""
    async with db_session.async_session_maker() as db:
        org = Workspace(type="organization", name="Orbit Demo Org")
        db.add(org)
        await db.flush()
        agent_workspace = AgentWorkspace(
            organization_workspace_id=org.id,
            key="delivery",
            name="Product Delivery",
            agent_profile="product_delivery",
        )
        db.add(agent_workspace)
        await db.commit()
        return agent_workspace.id


@pytest.mark.asyncio
async def test_my_membership_denies_org_member_without_agent_workspace_membership(client, auth_headers):
    """Alice is an active member of the ORGANIZATION workspace but was never added to the
    AgentWorkspace itself - resolve_agent_scope's WORKSPACE branch must still deny her."""
    agent_workspace_id = await _make_org_and_agent_workspace()
    alice_id = await _user_id("alice@example.com")
    async with db_session.async_session_maker() as db:
        agent_workspace = await db.get(AgentWorkspace, agent_workspace_id)
        db.add(WorkspaceMembership(workspace_id=agent_workspace.organization_workspace_id, user_id=alice_id, role="member"))
        await db.commit()

    resp = await client.get(f"/api/v1/agent-workspaces/{agent_workspace_id}/my-membership", headers=auth_headers)

    assert resp.status_code == 403
    assert "agent workspace" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_my_membership_403_does_not_distinguish_nonexistent_from_unauthorized(client, auth_headers):
    """The whole point of the endpoint: a caller must not be able to tell "this id doesn't exist"
    apart from "this id exists but you have no access to it" - both would otherwise leak which
    agent workspaces are real. Same status code AND same response body for both."""
    real_agent_workspace_id = await _make_org_and_agent_workspace()

    real_but_unauthorized = await client.get(
        f"/api/v1/agent-workspaces/{real_agent_workspace_id}/my-membership", headers=auth_headers
    )
    nonexistent = await client.get(
        "/api/v1/agent-workspaces/does-not-exist/my-membership", headers=auth_headers
    )

    assert real_but_unauthorized.status_code == 403
    assert nonexistent.status_code == 403
    assert real_but_unauthorized.json() == nonexistent.json()


@pytest.mark.asyncio
async def test_my_membership_requires_auth(client):
    resp = await client.get("/api/v1/agent-workspaces/some-id/my-membership")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_my_membership_allows_active_member_and_returns_business_role(client, auth_headers):
    agent_workspace_id = await _make_org_and_agent_workspace()
    alice_id = await _user_id("alice@example.com")
    async with db_session.async_session_maker() as db:
        agent_workspace = await db.get(AgentWorkspace, agent_workspace_id)
        db.add(WorkspaceMembership(workspace_id=agent_workspace.organization_workspace_id, user_id=alice_id, role="member"))
        db.add(AgentWorkspaceMembership(agent_workspace_id=agent_workspace_id, user_id=alice_id, business_role="lead"))
        await db.commit()

    resp = await client.get(f"/api/v1/agent-workspaces/{agent_workspace_id}/my-membership", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body == {"agent_workspace_id": agent_workspace_id, "business_role": "lead"}


@pytest.mark.asyncio
async def test_mine_true_lists_only_agent_workspaces_the_caller_actively_belongs_to(client, auth_headers, other_auth_headers):
    mine_id = await _make_org_and_agent_workspace()
    not_mine_id = await _make_org_and_agent_workspace()
    alice_id = await _user_id("alice@example.com")
    bob_id = await _user_id("bob@example.com")
    async with db_session.async_session_maker() as db:
        mine = await db.get(AgentWorkspace, mine_id)
        not_mine = await db.get(AgentWorkspace, not_mine_id)
        db.add(WorkspaceMembership(workspace_id=mine.organization_workspace_id, user_id=alice_id, role="member"))
        db.add(AgentWorkspaceMembership(agent_workspace_id=mine_id, user_id=alice_id, business_role="member"))
        db.add(WorkspaceMembership(workspace_id=not_mine.organization_workspace_id, user_id=bob_id, role="member"))
        db.add(AgentWorkspaceMembership(agent_workspace_id=not_mine_id, user_id=bob_id, business_role="member"))
        await db.commit()

    resp = await client.get("/api/v1/agent-workspaces", params={"mine": "true"}, headers=auth_headers)

    assert resp.status_code == 200
    ids = [workspace["id"] for workspace in resp.json()]
    assert ids == [mine_id]


@pytest.mark.asyncio
async def test_mine_true_excludes_revoked_membership(client, auth_headers):
    agent_workspace_id = await _make_org_and_agent_workspace()
    alice_id = await _user_id("alice@example.com")
    async with db_session.async_session_maker() as db:
        agent_workspace = await db.get(AgentWorkspace, agent_workspace_id)
        db.add(WorkspaceMembership(workspace_id=agent_workspace.organization_workspace_id, user_id=alice_id, role="member"))
        db.add(
            AgentWorkspaceMembership(
                agent_workspace_id=agent_workspace_id, user_id=alice_id, business_role="member", status="revoked"
            )
        )
        await db.commit()

    resp = await client.get("/api/v1/agent-workspaces", params={"mine": "true"}, headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_mine_false_or_missing_is_rejected(client, auth_headers):
    resp = await client.get("/api/v1/agent-workspaces", headers=auth_headers)
    assert resp.status_code == 400
