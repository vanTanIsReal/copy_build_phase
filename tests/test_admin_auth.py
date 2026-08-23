import pytest

from src.config import get_settings

BOOTSTRAP_KEY = "test-bootstrap-key"


@pytest.fixture(autouse=True)
def _restore_bootstrap_key_after():
    """admin_bootstrap_key lives on the same @lru_cache'd Settings singleton as
    llm_provider/model_name (see tests/test_services/test_ai_config_service.py) - any test that
    sets it must restore the original value so later tests in the same session aren't affected."""
    settings = get_settings()
    original = settings.admin_bootstrap_key
    yield
    settings.admin_bootstrap_key = original


@pytest.mark.asyncio
async def test_admin_register_disabled_without_bootstrap_key(client):
    get_settings().admin_bootstrap_key = ""
    resp = await client.post(
        "/api/v1/auth/admin/register",
        json={
            "email": "firstadmin@example.com",
            "password": "password123",
            "display_name": "First Admin",
            "bootstrap_key": "anything",
        },
    )
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_admin_register_rejects_wrong_key(client):
    get_settings().admin_bootstrap_key = BOOTSTRAP_KEY
    resp = await client.post(
        "/api/v1/auth/admin/register",
        json={
            "email": "firstadmin@example.com",
            "password": "password123",
            "display_name": "First Admin",
            "bootstrap_key": "not-the-key",
        },
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_register_success(client):
    get_settings().admin_bootstrap_key = BOOTSTRAP_KEY
    resp = await client.post(
        "/api/v1/auth/admin/register",
        json={
            "email": "firstadmin@example.com",
            "password": "password123",
            "display_name": "First Admin",
            "bootstrap_key": BOOTSTRAP_KEY,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["role"] == "admin"
    assert "access_token" in body


@pytest.mark.asyncio
async def test_admin_register_rejects_once_an_admin_exists(client):
    get_settings().admin_bootstrap_key = BOOTSTRAP_KEY
    payload = {
        "email": "firstadmin@example.com",
        "password": "password123",
        "display_name": "First Admin",
        "bootstrap_key": BOOTSTRAP_KEY,
    }
    first = await client.post("/api/v1/auth/admin/register", json=payload)
    assert first.status_code == 200

    second = await client.post(
        "/api/v1/auth/admin/register",
        json={**payload, "email": "secondadmin@example.com"},
    )
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_admin_login_success(client):
    get_settings().admin_bootstrap_key = BOOTSTRAP_KEY
    await client.post(
        "/api/v1/auth/admin/register",
        json={
            "email": "admin2@example.com",
            "password": "password123",
            "display_name": "Admin Two",
            "bootstrap_key": BOOTSTRAP_KEY,
        },
    )
    resp = await client.post(
        "/api/v1/auth/admin/login", json={"email": "admin2@example.com", "password": "password123"}
    )
    assert resp.status_code == 200
    assert resp.json()["user"]["role"] == "admin"


@pytest.mark.asyncio
async def test_admin_login_rejects_non_admin(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "regular@example.com", "password": "password123", "display_name": "Regular"},
    )
    resp = await client.post(
        "/api/v1/auth/admin/login", json={"email": "regular@example.com", "password": "password123"}
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_login_wrong_password(client):
    get_settings().admin_bootstrap_key = BOOTSTRAP_KEY
    await client.post(
        "/api/v1/auth/admin/register",
        json={
            "email": "admin3@example.com",
            "password": "password123",
            "display_name": "Admin Three",
            "bootstrap_key": BOOTSTRAP_KEY,
        },
    )
    resp = await client.post("/api/v1/auth/admin/login", json={"email": "admin3@example.com", "password": "nope"})
    assert resp.status_code == 401
