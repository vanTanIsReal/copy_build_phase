import pytest


@pytest.mark.asyncio
async def test_create_and_list_memory(client, auth_headers):
    resp = await client.post(
        "/api/v1/memories",
        json={"category": "Preference", "title": "Prefers async standups", "detail": "Mentioned in #team-eng"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["category"] == "Preference"
    assert body["title"] == "Prefers async standups"

    resp = await client.get("/api/v1/memories", headers=auth_headers)
    assert resp.status_code == 200
    titles = [m["title"] for m in resp.json()]
    assert "Prefers async standups" in titles


@pytest.mark.asyncio
async def test_memories_require_auth(client):
    resp = await client.get("/api/v1/memories")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_update_memory(client, auth_headers):
    created = (
        await client.post(
            "/api/v1/memories", json={"category": "Work", "title": "Old title"}, headers=auth_headers
        )
    ).json()

    resp = await client.patch(
        f"/api/v1/memories/{created['id']}", json={"title": "New title"}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "New title"
    assert resp.json()["category"] == "Work"


@pytest.mark.asyncio
async def test_delete_memory(client, auth_headers):
    created = (
        await client.post(
            "/api/v1/memories", json={"category": "People", "title": "Throwaway"}, headers=auth_headers
        )
    ).json()

    resp = await client.delete(f"/api/v1/memories/{created['id']}", headers=auth_headers)
    assert resp.status_code == 204

    resp = await client.get("/api/v1/memories", headers=auth_headers)
    assert created["id"] not in [m["id"] for m in resp.json()]


@pytest.mark.asyncio
async def test_memory_not_visible_to_other_user(client, auth_headers, other_auth_headers):
    created = (
        await client.post(
            "/api/v1/memories", json={"category": "Work", "title": "Private memory"}, headers=auth_headers
        )
    ).json()

    resp = await client.get("/api/v1/memories", headers=other_auth_headers)
    assert created["id"] not in [m["id"] for m in resp.json()]

    resp = await client.patch(
        f"/api/v1/memories/{created['id']}", json={"title": "Hijacked"}, headers=other_auth_headers
    )
    assert resp.status_code == 404

    resp = await client.delete(f"/api/v1/memories/{created['id']}", headers=other_auth_headers)
    assert resp.status_code == 404
