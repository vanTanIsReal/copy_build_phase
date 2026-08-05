import pytest


@pytest.mark.asyncio
async def test_create_and_list_reminder(client, auth_headers):
    resp = await client.post(
        "/api/v1/reminders",
        json={"title": "Send report", "due_at_iso": "2026-08-10T15:00:00", "lead_minutes": 30},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Send report"
    assert body["status"] == "scheduled"
    assert body["source"] == "manual"

    resp = await client.get("/api/v1/reminders", headers=auth_headers)
    assert resp.status_code == 200
    titles = [r["title"] for r in resp.json()]
    assert "Send report" in titles


@pytest.mark.asyncio
async def test_reminders_require_auth(client):
    resp = await client.get("/api/v1/reminders")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_cancel_reminder(client, auth_headers):
    created = (
        await client.post(
            "/api/v1/reminders",
            json={"title": "Throwaway", "due_at_iso": "2026-08-10T15:00:00"},
            headers=auth_headers,
        )
    ).json()

    resp = await client.delete(f"/api/v1/reminders/{created['id']}", headers=auth_headers)
    assert resp.status_code == 204

    resp = await client.get("/api/v1/reminders", headers=auth_headers)
    cancelled = next(r for r in resp.json() if r["id"] == created["id"])
    assert cancelled["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_missing_reminder_404(client, auth_headers):
    resp = await client.delete("/api/v1/reminders/does-not-exist", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_reminder_not_visible_to_other_user(client, auth_headers, other_auth_headers):
    created = (
        await client.post(
            "/api/v1/reminders",
            json={"title": "Private reminder", "due_at_iso": "2026-08-10T15:00:00"},
            headers=auth_headers,
        )
    ).json()

    resp = await client.get("/api/v1/reminders", headers=other_auth_headers)
    assert created["id"] not in [r["id"] for r in resp.json()]

    resp = await client.delete(f"/api/v1/reminders/{created['id']}", headers=other_auth_headers)
    assert resp.status_code == 404
