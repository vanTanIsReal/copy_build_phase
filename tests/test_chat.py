import pytest


async def _other_user_id(client, other_auth_headers):
    resp = await client.get("/api/v1/auth/me", headers=other_auth_headers)
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_and_dedupe_direct_conversation(client, auth_headers, other_auth_headers):
    other_id = await _other_user_id(client, other_auth_headers)

    resp1 = await client.post(
        "/api/v1/conversations", json={"type": "direct", "participant_ids": [other_id]}, headers=auth_headers
    )
    assert resp1.status_code == 200
    conv1 = resp1.json()
    assert conv1["type"] == "direct"
    assert conv1["name"] == "Bob"

    resp2 = await client.post(
        "/api/v1/conversations", json={"type": "direct", "participant_ids": [other_id]}, headers=auth_headers
    )
    assert resp2.status_code == 200
    assert resp2.json()["id"] == conv1["id"]


@pytest.mark.asyncio
async def test_group_conversation_requires_name(client, auth_headers, other_auth_headers):
    other_id = await _other_user_id(client, other_auth_headers)
    resp = await client.post(
        "/api/v1/conversations", json={"type": "group", "participant_ids": [other_id]}, headers=auth_headers
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_group_conversation_with_name(client, auth_headers, other_auth_headers):
    other_id = await _other_user_id(client, other_auth_headers)
    resp = await client.post(
        "/api/v1/conversations",
        json={"type": "group", "participant_ids": [other_id], "name": "Team"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "group"
    assert body["name"] == "Team"
    assert len(body["participants"]) == 2


@pytest.mark.asyncio
async def test_send_and_list_messages(client, auth_headers, other_auth_headers):
    other_id = await _other_user_id(client, other_auth_headers)
    conv = (
        await client.post(
            "/api/v1/conversations", json={"type": "direct", "participant_ids": [other_id]}, headers=auth_headers
        )
    ).json()

    send_resp = await client.post(
        f"/api/v1/conversations/{conv['id']}/messages", json={"content": "hello"}, headers=auth_headers
    )
    assert send_resp.status_code == 200
    assert send_resp.json()["content"] == "hello"

    history = await client.get(f"/api/v1/conversations/{conv['id']}/messages", headers=auth_headers)
    assert history.status_code == 200
    body = history.json()
    assert len(body["messages"]) == 1
    assert body["messages"][0]["content"] == "hello"
    assert body["has_more"] is False


@pytest.mark.asyncio
async def test_unread_count_and_mark_read(client, auth_headers, other_auth_headers):
    other_id = await _other_user_id(client, other_auth_headers)
    conv = (
        await client.post(
            "/api/v1/conversations", json={"type": "direct", "participant_ids": [other_id]}, headers=auth_headers
        )
    ).json()
    await client.post(f"/api/v1/conversations/{conv['id']}/messages", json={"content": "hi bob"}, headers=auth_headers)

    listed = await client.get("/api/v1/conversations", headers=other_auth_headers)
    summary = next(c for c in listed.json()["conversations"] if c["id"] == conv["id"])
    assert summary["unread_count"] == 1

    await client.post(f"/api/v1/conversations/{conv['id']}/read", headers=other_auth_headers)
    listed_again = await client.get("/api/v1/conversations", headers=other_auth_headers)
    summary_again = next(c for c in listed_again.json()["conversations"] if c["id"] == conv["id"])
    assert summary_again["unread_count"] == 0


@pytest.mark.asyncio
async def test_non_participant_forbidden(client, auth_headers, other_auth_headers):
    other_id = await _other_user_id(client, other_auth_headers)
    conv = (
        await client.post(
            "/api/v1/conversations", json={"type": "direct", "participant_ids": [other_id]}, headers=auth_headers
        )
    ).json()

    third = await client.post(
        "/api/v1/auth/register",
        json={"email": "carol@example.com", "password": "password123", "display_name": "Carol"},
    )
    carol_headers = {"Authorization": f"Bearer {third.json()['access_token']}"}

    resp = await client.get(f"/api/v1/conversations/{conv['id']}/messages", headers=carol_headers)
    assert resp.status_code == 403

    resp2 = await client.post(
        f"/api/v1/conversations/{conv['id']}/messages", json={"content": "hey"}, headers=carol_headers
    )
    assert resp2.status_code == 403


@pytest.mark.asyncio
async def test_list_users_excludes_self(client, auth_headers, other_auth_headers):
    resp = await client.get("/api/v1/users", headers=auth_headers)
    assert resp.status_code == 200
    emails = [u["email"] for u in resp.json()]
    assert "bob@example.com" in emails
    assert "alice@example.com" not in emails


# ---------------------------------------------------------------- delete (hide) conversation


async def _ids(resp):
    return {c["id"] for c in resp.json()["conversations"]}


@pytest.mark.asyncio
async def test_delete_conversation_hides_it_for_caller_only(client, auth_headers, other_auth_headers):
    other_id = await _other_user_id(client, other_auth_headers)
    conv = (
        await client.post(
            "/api/v1/conversations", json={"type": "direct", "participant_ids": [other_id]}, headers=auth_headers
        )
    ).json()

    resp = await client.delete(f"/api/v1/conversations/{conv['id']}", headers=auth_headers)
    assert resp.status_code == 204

    assert conv["id"] not in await _ids(await client.get("/api/v1/conversations", headers=auth_headers))
    assert conv["id"] in await _ids(await client.get("/api/v1/conversations", headers=other_auth_headers))


@pytest.mark.asyncio
async def test_delete_conversation_reappears_after_new_message(client, auth_headers, other_auth_headers):
    other_id = await _other_user_id(client, other_auth_headers)
    conv = (
        await client.post(
            "/api/v1/conversations", json={"type": "direct", "participant_ids": [other_id]}, headers=auth_headers
        )
    ).json()
    await client.delete(f"/api/v1/conversations/{conv['id']}", headers=auth_headers)

    await client.post(f"/api/v1/conversations/{conv['id']}/messages", json={"content": "hi"}, headers=other_auth_headers)

    assert conv["id"] in await _ids(await client.get("/api/v1/conversations", headers=auth_headers))


@pytest.mark.asyncio
async def test_delete_conversation_requires_participant(client, auth_headers, other_auth_headers):
    other_id = await _other_user_id(client, other_auth_headers)
    conv = (
        await client.post(
            "/api/v1/conversations", json={"type": "direct", "participant_ids": [other_id]}, headers=auth_headers
        )
    ).json()

    third = await client.post(
        "/api/v1/auth/register",
        json={"email": "carol2@example.com", "password": "password123", "display_name": "Carol"},
    )
    carol_headers = {"Authorization": f"Bearer {third.json()['access_token']}"}

    resp = await client.delete(f"/api/v1/conversations/{conv['id']}", headers=carol_headers)
    assert resp.status_code == 403


# ---------------------------------------------------------------- leave group


@pytest.mark.asyncio
async def test_leave_group_removes_member_and_notifies_others(client, auth_headers, other_auth_headers):
    other_id = await _other_user_id(client, other_auth_headers)
    conv = (
        await client.post(
            "/api/v1/conversations",
            json={"type": "group", "participant_ids": [other_id], "name": "Team"},
            headers=auth_headers,
        )
    ).json()

    resp = await client.post(f"/api/v1/conversations/{conv['id']}/leave", headers=other_auth_headers)
    assert resp.status_code == 204

    # The leaver loses access outright (not just hidden from their list).
    assert (await client.get(f"/api/v1/conversations/{conv['id']}/messages", headers=other_auth_headers)).status_code == 403

    # The remaining member's roster reflects the departure.
    listed = await client.get("/api/v1/conversations", headers=auth_headers)
    summary = next(c for c in listed.json()["conversations"] if c["id"] == conv["id"])
    assert len(summary["participants"]) == 1


@pytest.mark.asyncio
async def test_leave_group_last_member_deletes_conversation(client, auth_headers, other_auth_headers):
    other_id = await _other_user_id(client, other_auth_headers)
    conv = (
        await client.post(
            "/api/v1/conversations",
            json={"type": "group", "participant_ids": [other_id], "name": "Team"},
            headers=auth_headers,
        )
    ).json()

    await client.post(f"/api/v1/conversations/{conv['id']}/leave", headers=other_auth_headers)
    resp = await client.post(f"/api/v1/conversations/{conv['id']}/leave", headers=auth_headers)
    assert resp.status_code == 204

    # Nobody left to be a participant of it - the conversation itself is gone.
    assert (await client.get(f"/api/v1/conversations/{conv['id']}/messages", headers=auth_headers)).status_code == 403


@pytest.mark.asyncio
async def test_leave_direct_conversation_rejected(client, auth_headers, other_auth_headers):
    other_id = await _other_user_id(client, other_auth_headers)
    conv = (
        await client.post(
            "/api/v1/conversations", json={"type": "direct", "participant_ids": [other_id]}, headers=auth_headers
        )
    ).json()

    resp = await client.post(f"/api/v1/conversations/{conv['id']}/leave", headers=auth_headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_leave_group_requires_participant(client, auth_headers, other_auth_headers):
    other_id = await _other_user_id(client, other_auth_headers)
    conv = (
        await client.post(
            "/api/v1/conversations",
            json={"type": "group", "participant_ids": [other_id], "name": "Team"},
            headers=auth_headers,
        )
    ).json()

    third = await client.post(
        "/api/v1/auth/register",
        json={"email": "carol3@example.com", "password": "password123", "display_name": "Carol"},
    )
    carol_headers = {"Authorization": f"Bearer {third.json()['access_token']}"}

    resp = await client.post(f"/api/v1/conversations/{conv['id']}/leave", headers=carol_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_leave_group_nonexistent_conversation(client, auth_headers):
    resp = await client.post("/api/v1/conversations/does-not-exist/leave", headers=auth_headers)
    assert resp.status_code == 404
