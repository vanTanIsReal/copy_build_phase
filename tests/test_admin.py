import pytest

from src.services import reminder_service
from src.services.scheduler import scheduler


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
async def test_non_admin_cannot_update_budget(client, auth_headers):
    resp = await client.patch("/api/v1/admin/settings/budget", json={"daily_token_budget": 5000}, headers=auth_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_update_budget_and_it_reflects_in_stats(client, admin_auth_headers):
    resp = await client.patch(
        "/api/v1/admin/settings/budget", json={"daily_token_budget": 5000}, headers=admin_auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["daily_token_budget"] == 5000

    stats_resp = await client.get("/api/v1/admin/stats", headers=admin_auth_headers)
    assert stats_resp.json()["daily_token_budget"] == 5000


@pytest.mark.asyncio
async def test_update_budget_rejects_negative_value(client, admin_auth_headers):
    resp = await client.patch(
        "/api/v1/admin/settings/budget", json={"daily_token_budget": -1}, headers=admin_auth_headers
    )
    assert resp.status_code == 422


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


@pytest.mark.asyncio
async def test_non_admin_cannot_access_new_admin_routes(client, auth_headers):
    for path in ("/api/v1/admin/tasks", "/api/v1/admin/reminders", "/api/v1/admin/memories"):
        resp = await client.get(path, headers=auth_headers)
        assert resp.status_code == 403, path


@pytest.mark.asyncio
async def test_admin_can_list_and_delete_tasks(client, admin_auth_headers, auth_headers):
    alice = (await client.get("/api/v1/auth/me", headers=auth_headers)).json()
    created = (
        await client.post("/api/v1/tasks", json={"title": "Admin-visible task"}, headers=auth_headers)
    ).json()

    resp = await client.get("/api/v1/admin/tasks", headers=admin_auth_headers)
    assert resp.status_code == 200
    listed = next(t for t in resp.json() if t["id"] == created["id"])
    assert listed["owner_id"] == alice["id"]
    assert listed["owner_email"] == "alice@example.com"
    assert listed["owner_display_name"] == alice["display_name"]
    assert listed["conversation_label"] is None

    resp = await client.delete(f"/api/v1/admin/tasks/{created['id']}", headers=admin_auth_headers)
    assert resp.status_code == 204

    resp = await client.get("/api/v1/tasks", headers=auth_headers)
    assert created["id"] not in [t["id"] for t in resp.json()]


@pytest.mark.asyncio
async def test_admin_tasks_owner_filter(client, admin_auth_headers, auth_headers, other_auth_headers):
    alice = (await client.get("/api/v1/auth/me", headers=auth_headers)).json()
    await client.post("/api/v1/tasks", json={"title": "Alice task"}, headers=auth_headers)
    await client.post("/api/v1/tasks", json={"title": "Bob task"}, headers=other_auth_headers)

    resp = await client.get(f"/api/v1/admin/tasks?owner_id={alice['id']}", headers=admin_auth_headers)
    assert resp.status_code == 200
    owners = {t["owner_id"] for t in resp.json()}
    assert owners == {alice["id"]}


@pytest.mark.asyncio
async def test_admin_can_list_and_delete_memories(client, admin_auth_headers, auth_headers):
    alice = (await client.get("/api/v1/auth/me", headers=auth_headers)).json()
    created = (
        await client.post(
            "/api/v1/memories", json={"category": "Work", "title": "Admin-visible memory"}, headers=auth_headers
        )
    ).json()

    resp = await client.get("/api/v1/admin/memories", headers=admin_auth_headers)
    assert resp.status_code == 200
    listed = next(m for m in resp.json() if m["id"] == created["id"])
    assert listed["owner_id"] == alice["id"]
    assert listed["owner_email"] == "alice@example.com"

    resp = await client.delete(f"/api/v1/admin/memories/{created['id']}", headers=admin_auth_headers)
    assert resp.status_code == 204

    resp = await client.get("/api/v1/memories", headers=auth_headers)
    assert created["id"] not in [m["id"] for m in resp.json()]


@pytest.mark.asyncio
async def test_admin_can_list_and_delete_reminders_and_cancels_scheduler_job(
    client, admin_auth_headers, auth_headers
):
    alice = (await client.get("/api/v1/auth/me", headers=auth_headers)).json()
    created = (
        await client.post(
            "/api/v1/reminders",
            json={"title": "Admin-visible reminder", "due_at_iso": "2026-08-10T15:00:00"},
            headers=auth_headers,
        )
    ).json()
    assert scheduler.get_job(created["id"]) is not None

    resp = await client.get("/api/v1/admin/reminders", headers=admin_auth_headers)
    assert resp.status_code == 200
    listed = next(r for r in resp.json() if r["id"] == created["id"])
    assert listed["owner_id"] == alice["id"]
    assert listed["owner_email"] == "alice@example.com"
    assert listed["status"] == "scheduled"

    resp = await client.delete(f"/api/v1/admin/reminders/{created['id']}", headers=admin_auth_headers)
    assert resp.status_code == 204

    # Hard-deleted (unlike the user-facing DELETE, which only soft-cancels) and the underlying
    # APScheduler job must actually be gone, not just the DB row.
    assert scheduler.get_job(created["id"]) is None
    resp = await client.get("/api/v1/reminders", headers=auth_headers)
    assert created["id"] not in [r["id"] for r in resp.json()]


@pytest.mark.asyncio
async def test_admin_delete_reminder_404_when_missing(client, admin_auth_headers):
    resp = await client.delete("/api/v1/admin/reminders/does-not-exist", headers=admin_auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_reminders_include_ownerless_reminders(client, admin_auth_headers):
    reminder = await reminder_service.schedule_reminder(
        owner_id=None, title="Agent reminder", due_at_iso="2026-08-10T15:00:00", source="agent"
    )

    resp = await client.get("/api/v1/admin/reminders", headers=admin_auth_headers)
    assert resp.status_code == 200
    listed = next(r for r in resp.json() if r["id"] == reminder.id)
    assert listed["owner_id"] is None
    assert listed["owner_email"] is None
    assert listed["owner_display_name"] is None


# ---------------------------------------------------------------- system health / AI management / AI usage / audit log


@pytest.mark.asyncio
async def test_non_admin_cannot_access_ai_platform_routes(client, auth_headers):
    for path in ("/api/v1/admin/system-health", "/api/v1/admin/ai-management", "/api/v1/admin/ai-usage", "/api/v1/admin/audit-log"):
        resp = await client.get(path, headers=auth_headers)
        assert resp.status_code == 403, path


@pytest.mark.asyncio
async def test_admin_can_view_system_health(client, admin_auth_headers):
    resp = await client.get("/api/v1/admin/system-health", headers=admin_auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["overall_status"] in ("operational", "degraded", "down")
    keys = {c["key"] for c in body["components"]}
    assert {"database", "scheduler", "websocket", "llm", "calendar"} <= keys


@pytest.mark.asyncio
async def test_admin_can_view_ai_management(client, admin_auth_headers):
    resp = await client.get("/api/v1/admin/ai-management", headers=admin_auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"]
    assert body["model"]
    assert "model_options" in body
    assert isinstance(body["configured_providers"], list)


@pytest.mark.asyncio
async def test_admin_can_update_ai_management(client, admin_auth_headers):
    """Test .env configures all 3 providers, so google/gemini-2.5-flash is always selectable."""
    resp = await client.patch(
        "/api/v1/admin/ai-management",
        json={"provider": "google", "model": "gemini-2.5-flash", "temperature": 0.4},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "google"
    assert body["model"] == "gemini-2.5-flash"
    assert body["temperature"] == 0.4

    # Reflected back on a plain GET too, not just the PATCH response.
    again = await client.get("/api/v1/admin/ai-management", headers=admin_auth_headers)
    assert again.json()["provider"] == "google"
    assert again.json()["model"] == "gemini-2.5-flash"


@pytest.mark.asyncio
async def test_ai_management_rejects_unsupported_model(client, admin_auth_headers):
    resp = await client.patch(
        "/api/v1/admin/ai-management",
        json={"provider": "google", "model": "not-a-real-model", "temperature": 0.7},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ai_management_rejects_unconfigured_provider(client, admin_auth_headers, monkeypatch):
    from src.services import ai_config_service

    monkeypatch.setattr(ai_config_service, "configured_providers", lambda: ["google"])
    resp = await client.patch(
        "/api/v1/admin/ai-management",
        json={"provider": "openai", "model": "gpt-4o-mini", "temperature": 0.7},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_admin_can_view_ai_usage_report(client, admin_auth_headers):
    from src.services import usage_service

    await usage_service.log_usage(
        provider="google", model="gemini-2.5-flash", usage_metadata={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}
    )

    resp = await client.get("/api/v1/admin/ai-usage?days=7", headers=admin_auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["days"] == 7
    assert body["totals"]["total_tokens"] >= 150
    assert len(body["daily"]) == 7
    today = body["daily"][-1]
    assert today["total_tokens"] >= 150
    model_row = next(m for m in body["models"] if m["provider"] == "google" and m["model"] == "gemini-2.5-flash")
    assert model_row["total_tokens"] >= 150
    assert model_row["estimated_cost_usd"] > 0  # gemini-2.5-flash is in the priced table


@pytest.mark.asyncio
async def test_admin_actions_are_recorded_in_audit_log(client, admin_auth_headers, auth_headers):
    alice = (await client.get("/api/v1/auth/me", headers=auth_headers)).json()
    await client.patch(f"/api/v1/admin/users/{alice['id']}/role", json={"role": "admin"}, headers=admin_auth_headers)
    await client.patch(f"/api/v1/admin/users/{alice['id']}/role", json={"role": "user"}, headers=admin_auth_headers)
    await client.patch("/api/v1/admin/settings/budget", json={"daily_token_budget": 12345}, headers=admin_auth_headers)

    resp = await client.get("/api/v1/admin/audit-log", headers=admin_auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    actions = [item["action"] for item in body["items"]]
    assert actions.count("user.role_changed") == 2
    assert "platform.budget_changed" in actions
    role_change = next(item for item in body["items"] if item["action"] == "user.role_changed")
    assert role_change["actor_type"] == "admin"
    assert role_change["actor_email"] == "admin@example.com"
    assert role_change["target_type"] == "user"
    assert role_change["target_id"] == alice["id"]


@pytest.mark.asyncio
async def test_audit_log_filters_by_query_and_actor_type(client, admin_auth_headers, auth_headers):
    task = (await client.post("/api/v1/tasks", json={"title": "To be deleted"}, headers=auth_headers)).json()
    await client.delete(f"/api/v1/admin/tasks/{task['id']}", headers=admin_auth_headers)

    resp = await client.get("/api/v1/admin/audit-log?q=task.deleted", headers=admin_auth_headers)
    assert resp.status_code == 200
    assert all(item["action"] == "task.deleted" for item in resp.json()["items"])
    assert any(item["target_id"] == task["id"] for item in resp.json()["items"])

    resp = await client.get("/api/v1/admin/audit-log?actor_type=system", headers=admin_auth_headers)
    assert resp.status_code == 200
    assert resp.json()["items"] == []  # nothing logs as "system" yet - every call site is an admin action


@pytest.mark.asyncio
async def test_deleting_memory_reminder_conversation_are_all_audited(
    client, admin_auth_headers, auth_headers, other_auth_headers
):
    memory = (
        await client.post("/api/v1/memories", json={"category": "Work", "title": "M"}, headers=auth_headers)
    ).json()
    reminder = (
        await client.post(
            "/api/v1/reminders", json={"title": "R", "due_at_iso": "2026-08-10T15:00:00"}, headers=auth_headers
        )
    ).json()
    bob = (await client.get("/api/v1/auth/me", headers=other_auth_headers)).json()
    conv = (
        await client.post(
            "/api/v1/conversations", json={"type": "direct", "participant_ids": [bob["id"]]}, headers=auth_headers
        )
    ).json()

    await client.delete(f"/api/v1/admin/memories/{memory['id']}", headers=admin_auth_headers)
    await client.delete(f"/api/v1/admin/reminders/{reminder['id']}", headers=admin_auth_headers)
    await client.delete(f"/api/v1/admin/conversations/{conv['id']}", headers=admin_auth_headers)

    resp = await client.get("/api/v1/admin/audit-log", headers=admin_auth_headers)
    actions_and_targets = {(item["action"], item["target_id"]) for item in resp.json()["items"]}
    assert ("memory.deleted", memory["id"]) in actions_and_targets
    assert ("reminder.deleted", reminder["id"]) in actions_and_targets
    assert ("conversation.deleted", conv["id"]) in actions_and_targets
