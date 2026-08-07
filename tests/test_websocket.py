import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.main import app


@pytest.fixture
def ws_client(client, monkeypatch):
    """Sync TestClient sharing the async `client` fixture's in-memory DB.

    Websockets need Starlette's sync TestClient (httpx's AsyncClient/ASGITransport doesn't
    support them). Entering it as a context manager fires app lifespan, so `init_db()` is
    stubbed out here - the in-memory DB/tables already exist via the `client` fixture, and we
    don't want lifespan touching the real on-disk database during tests. Same reasoning for
    `scheduler.start()`/`.shutdown()` - its SQLAlchemyJobStore would otherwise create a real
    `apscheduler_jobs` table in the on-disk DB just from the lifespan firing.
    """

    async def _noop_init_db():
        return None

    monkeypatch.setattr("src.main.init_db", _noop_init_db)
    monkeypatch.setattr("src.main.scheduler.start", lambda *a, **k: None)
    monkeypatch.setattr("src.main.scheduler.shutdown", lambda *a, **k: None)
    with TestClient(app) as tc:
        yield tc


@pytest.mark.asyncio
async def test_websocket_rejects_invalid_token(ws_client):
    with pytest.raises(WebSocketDisconnect):
        with ws_client.websocket_connect("/api/v1/ws?token=not-a-real-token"):
            pass


@pytest.mark.asyncio
async def test_websocket_send_broadcasts_to_participant(client, auth_headers, other_auth_headers, ws_client):
    alice = (await client.get("/api/v1/auth/me", headers=auth_headers)).json()
    bob = (await client.get("/api/v1/auth/me", headers=other_auth_headers)).json()
    alice_token = auth_headers["Authorization"].split(" ")[1]
    bob_token = other_auth_headers["Authorization"].split(" ")[1]

    conv = (
        await client.post(
            "/api/v1/conversations", json={"type": "direct", "participant_ids": [bob["id"]]}, headers=auth_headers
        )
    ).json()

    with ws_client.websocket_connect(f"/api/v1/ws?token={alice_token}") as alice_ws:
        with ws_client.websocket_connect(f"/api/v1/ws?token={bob_token}") as bob_ws:
            alice_ws.send_json({"type": "send_message", "conversation_id": conv["id"], "content": "hi bob"})
            received = bob_ws.receive_json()
            assert received["type"] == "new_message"
            assert received["message"]["content"] == "hi bob"
            assert received["message"]["sender_id"] == alice["id"]

    history = await client.get(f"/api/v1/conversations/{conv['id']}/messages", headers=auth_headers)
    assert any(m["content"] == "hi bob" for m in history.json()["messages"])
