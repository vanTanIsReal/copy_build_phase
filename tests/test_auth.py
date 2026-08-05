from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_register_success(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "new@example.com", "password": "password123", "display_name": "New User"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "new@example.com"
    assert body["user"]["display_name"] == "New User"


@pytest.mark.asyncio
async def test_register_duplicate_email(client):
    payload = {"email": "dup@example.com", "password": "password123", "display_name": "Dup"}
    await client.post("/api/v1/auth/register", json=payload)
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_login_success(client):
    payload = {"email": "login@example.com", "password": "password123", "display_name": "Login"}
    await client.post("/api/v1/auth/register", json=payload)
    resp = await client.post("/api/v1/auth/login", json={"email": payload["email"], "password": payload["password"]})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    payload = {"email": "wrong@example.com", "password": "password123", "display_name": "Wrong"}
    await client.post("/api/v1/auth/register", json=payload)
    resp = await client.post("/api/v1/auth/login", json={"email": payload["email"], "password": "nope"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_token(client):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_me_with_token(client, auth_headers):
    resp = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "alice@example.com"


@pytest.mark.asyncio
async def test_login_promotes_existing_user_to_initial_admin(client, monkeypatch):
    payload = {"email": "admin@example.com", "password": "password123", "display_name": "Admin User"}
    await client.post("/api/v1/auth/register", json=payload)

    monkeypatch.setattr(
        "src.api.auth_routes.get_settings",
        lambda: SimpleNamespace(initial_admin_email="admin@example.com"),
    )

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )

    assert resp.status_code == 200
    assert resp.json()["user"]["role"] == "admin"


@pytest.mark.asyncio
async def test_forgot_password_resets_password_once(client):
    payload = {"email": "reset@example.com", "password": "password123", "display_name": "Reset User"}
    await client.post("/api/v1/auth/register", json=payload)

    forgot = await client.post("/api/v1/auth/forgot-password", json={"email": payload["email"]})
    assert forgot.status_code == 200
    reset_token = forgot.json()["reset_token"]
    assert reset_token

    reset = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_token, "password": "new-password123"},
    )
    assert reset.status_code == 200

    old_login = await client.post(
        "/api/v1/auth/login", json={"email": payload["email"], "password": payload["password"]}
    )
    new_login = await client.post(
        "/api/v1/auth/login", json={"email": payload["email"], "password": "new-password123"}
    )
    assert old_login.status_code == 401
    assert new_login.status_code == 200

    reused = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_token, "password": "another-password123"},
    )
    assert reused.status_code == 400


@pytest.mark.asyncio
async def test_forgot_password_does_not_reveal_unknown_email(client):
    resp = await client.post("/api/v1/auth/forgot-password", json={"email": "missing@example.com"})
    assert resp.status_code == 200
    assert resp.json()["reset_token"] is None
    assert "If an account exists" in resp.json()["message"]


@pytest.mark.asyncio
async def test_reset_password_rejects_invalid_token(client):
    resp = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": "invalid-token-that-is-long-enough", "password": "new-password123"},
    )
    assert resp.status_code == 400
