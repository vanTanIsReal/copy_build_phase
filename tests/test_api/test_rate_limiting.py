import pytest

from src.api.rate_limit import request_limiter
from src.services import usage_service


@pytest.fixture(autouse=True)
def _enable_rate_limiting(monkeypatch):
    monkeypatch.setattr(request_limiter, "enabled", True)
    request_limiter.reset()
    yield
    request_limiter.reset()


@pytest.mark.asyncio
async def test_register_is_rate_limited_per_ip(client):
    for index in range(5):
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": f"rate-register-{index}@example.com",
                "password": "password123",
                "display_name": "Rate Test",
            },
        )
        assert response.status_code == 201
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "rate-register-overflow@example.com",
            "password": "password123",
            "display_name": "Rate Test",
        },
    )
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0


@pytest.mark.asyncio
async def test_chat_is_rate_limited_per_user(client, auth_headers, monkeypatch):
    async def _over_budget():
        return True

    monkeypatch.setattr(usage_service, "is_over_budget", _over_budget)
    for _ in range(15):
        response = await client.post("/api/v1/chat", json={"message": "hello"}, headers=auth_headers)
        assert response.status_code == 200
    response = await client.post("/api/v1/chat", json={"message": "hello"}, headers=auth_headers)
    assert response.status_code == 429


@pytest.mark.asyncio
async def test_health_is_exempt(client):
    for _ in range(70):
        assert (await client.get("/health")).status_code == 200
