"""Tests for src/api/rate_limit.py - the slowapi wiring in src/main.py and the per-route tiers
decorated in src/api/auth_routes.py / src/api/routes.py.

The limiter is OFF by default across the whole test session (tests/conftest.py sets
RATE_LIMIT_ENABLED=false before src.main.app is imported) so the rest of the suite - which
registers several users per test via auth_headers/admin_auth_headers/other_auth_headers - doesn't
trip the register/login limits against itself. This file explicitly re-enables the limiter for its
own tests and resets its in-memory storage before/after each one, since `app` (and therefore
`app.state.limiter`) is one object reused for the entire pytest session.

Limit *values* here are whatever RATE_LIMIT_* actually resolves to for the test process (the
project defaults: register=5/minute, auth=10/minute, chat=15/minute, crud=60/minute - see
src/config.py) - the decorators bake these in at import time, so tests drive real request counts
past the real thresholds rather than trying to shrink the thresholds at test time.
"""

import pytest

from src.api.rate_limit import limiter
from src.services import usage_service


@pytest.fixture(autouse=True)
def _enable_rate_limiting(monkeypatch):
    monkeypatch.setattr(limiter, "enabled", True)
    limiter.reset()
    yield
    limiter.reset()


@pytest.mark.asyncio
async def test_register_rate_limited_per_ip(client):
    for i in range(5):
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": f"ratelimit-reg-{i}@example.com", "password": "password123", "display_name": "T"},
        )
        assert resp.status_code == 200, resp.text

    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "ratelimit-reg-overflow@example.com", "password": "password123", "display_name": "T"},
    )
    assert resp.status_code == 429
    assert "error" in resp.json()


@pytest.mark.asyncio
async def test_login_rate_limited_per_ip(client):
    # Wrong password still hits the endpoint (and is counted) before it ever checks credentials -
    # the rate limit is enforced by the decorator wrapper, ahead of the route body.
    for _ in range(10):
        resp = await client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "wrong"})
        assert resp.status_code == 401

    resp = await client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "wrong"})
    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_chat_rate_limited_per_user(client, auth_headers, monkeypatch):
    # Force the budget-block early-return in POST /chat so this never needs a live/mocked LLM -
    # the rate-limit check runs before that branch, so hits still count against the chat limit.
    async def _over_budget():
        return True

    monkeypatch.setattr(usage_service, "is_over_budget", _over_budget)

    for _ in range(15):
        resp = await client.post("/api/v1/chat", json={"message": "hi"}, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"

    resp = await client.post("/api/v1/chat", json={"message": "hi"}, headers=auth_headers)
    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_chat_resume_never_rate_limited(client, auth_headers):
    # Burst well past every other tier's threshold - resume is exempt (@limiter.exempt in
    # src/api/routes.py), so it should never 429 no matter the volume. Each call fails for an
    # unrelated reason (no such thread_id was ever started, so there's nothing to resume) rather
    # than succeeding - fine, we're only asserting it's never blocked by the *rate limiter*.
    for _ in range(70):
        resp = await client.post(
            "/api/v1/chat/resume",
            json={"thread_id": "does-not-exist", "approved": False},
            headers=auth_headers,
        )
        assert resp.status_code != 429


@pytest.mark.asyncio
async def test_health_never_rate_limited(client):
    for _ in range(70):
        resp = await client.get("/health")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_crud_default_tier_rate_limited_per_user(client, auth_headers, other_auth_headers):
    # Default 60/minute tier applied automatically by SlowAPIMiddleware to any route with neither
    # its own @limiter.limit(...) nor @limiter.exempt - GET /memories is a plain example.
    for _ in range(60):
        resp = await client.get("/api/v1/memories", headers=auth_headers)
        assert resp.status_code == 200

    resp = await client.get("/api/v1/memories", headers=auth_headers)
    assert resp.status_code == 429

    # A different user has an independent bucket (keyed by user id, not shared per-process/IP) -
    # still succeeds right after the first user got blocked.
    resp = await client.get("/api/v1/memories", headers=other_auth_headers)
    assert resp.status_code == 200
