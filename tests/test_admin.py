import pytest


@pytest.mark.asyncio
async def test_me_includes_role(client, auth_headers):
    resp = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["role"] == "user"


@pytest.mark.asyncio
async def test_non_admin_cannot_access_admin_routes(client, auth_headers):
    resp = await client.get("/api/v1/admin/stats", headers=auth_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_view_stats(client, admin_auth_headers, auth_headers):
    resp = await client.get("/api/v1/admin/stats", headers=admin_auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_users"] >= 2
    assert "total_conversations" in body
    assert "total_messages" in body
    assert "new_users_last_7_days" in body


@pytest.mark.asyncio
async def test_admin_can_list_users(client, admin_auth_headers, auth_headers):
    resp = await client.get("/api/v1/admin/users", headers=admin_auth_headers)
    assert resp.status_code == 200
    emails = {u["email"] for u in resp.json()}
    assert "admin@example.com" in emails
    assert "alice@example.com" in emails


@pytest.mark.asyncio
async def test_admin_can_promote_and_demote_other_user(client, admin_auth_headers, auth_headers):
    users_resp = await client.get("/api/v1/admin/users", headers=admin_auth_headers)
    alice = next(u for u in users_resp.json() if u["email"] == "alice@example.com")

    resp = await client.patch(
        f"/api/v1/admin/users/{alice['id']}/role", json={"role": "admin"}, headers=admin_auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"

    resp = await client.patch(
        f"/api/v1/admin/users/{alice['id']}/role", json={"role": "user"}, headers=admin_auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "user"


@pytest.mark.asyncio
async def test_admin_cannot_change_own_role(client, admin_auth_headers):
    me = await client.get("/api/v1/auth/me", headers=admin_auth_headers)
    resp = await client.patch(
        f"/api/v1/admin/users/{me.json()['id']}/role", json={"role": "user"}, headers=admin_auth_headers
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_admin_cannot_deactivate_own_account(client, admin_auth_headers):
    me = await client.get("/api/v1/auth/me", headers=admin_auth_headers)
    resp = await client.patch(
        f"/api/v1/admin/users/{me.json()['id']}/status", json={"is_active": False}, headers=admin_auth_headers
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_deactivated_user_loses_access(client, admin_auth_headers, auth_headers):
    users_resp = await client.get("/api/v1/admin/users", headers=admin_auth_headers)
    alice = next(u for u in users_resp.json() if u["email"] == "alice@example.com")

    resp = await client.patch(
        f"/api/v1/admin/users/{alice['id']}/status", json={"is_active": False}, headers=admin_auth_headers
    )
    assert resp.status_code == 200

    resp = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_list_and_view_conversations(client, admin_auth_headers, auth_headers, other_auth_headers):
    bob = (await client.get("/api/v1/auth/me", headers=other_auth_headers)).json()
    conv = (
        await client.post(
            "/api/v1/conversations", json={"type": "direct", "participant_ids": [bob["id"]]}, headers=auth_headers
        )
    ).json()

    resp = await client.get("/api/v1/admin/conversations", headers=admin_auth_headers)
    assert resp.status_code == 200
    listed = next(c for c in resp.json() if c["id"] == conv["id"])
    assert listed["participant_count"] == 2

    resp = await client.get(f"/api/v1/admin/conversations/{conv['id']}/messages", headers=admin_auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []

    resp = await client.delete(f"/api/v1/admin/conversations/{conv['id']}", headers=admin_auth_headers)
    assert resp.status_code == 204
