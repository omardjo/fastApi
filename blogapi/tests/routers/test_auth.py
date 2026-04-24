import pytest
from uuid import uuid4

from blogapi.database import auth_security_event_table, database
from blogapi.routers import auth as auth_router


def unique_email() -> str:
    return f"user-{uuid4().hex}@example.com"


@pytest.mark.anyio
async def test_register_returns_token(async_client):
    email = unique_email()
    response = await async_client.post(
        "/auth/register", json={"email": email, "password": "secret123"}
    )

    assert response.status_code == 201
    data = response.json()
    assert data["token_type"] == "bearer"
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["user"]["email"] == email
    assert isinstance(data["user"]["id"], int)


@pytest.mark.anyio
async def test_register_rejects_duplicate_username(async_client):
    payload = {"email": unique_email(), "password": "secret123"}

    first_response = await async_client.post("/auth/register", json=payload)
    second_response = await async_client.post("/auth/register", json=payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == "Email already exists"


@pytest.mark.anyio
async def test_login_returns_token(async_client):
    payload = {"email": unique_email(), "password": "secret123"}
    await async_client.post("/auth/register", json=payload)

    response = await async_client.post("/auth/login", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["user"]["email"] == payload["email"]


@pytest.mark.anyio
async def test_refresh_rotates_tokens(async_client):
    payload = {"email": unique_email(), "password": "secret123"}
    register_response = await async_client.post("/auth/register", json=payload)
    refresh_token = register_response.json()["refresh_token"]

    first_refresh = await async_client.post(
        "/auth/refresh", json={"refresh_token": refresh_token}
    )

    assert first_refresh.status_code == 200
    refreshed_data = first_refresh.json()
    assert refreshed_data["access_token"]
    assert refreshed_data["refresh_token"]
    assert refreshed_data["refresh_token"] != refresh_token

    reused_token_response = await async_client.post(
        "/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert reused_token_response.status_code == 401


@pytest.mark.anyio
async def test_login_rejects_invalid_credentials(async_client):
    email = unique_email()
    await async_client.post(
        "/auth/register", json={"email": email, "password": "secret123"}
    )

    response = await async_client.post(
        "/auth/login", json={"email": email, "password": "wrong-password"}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


@pytest.mark.anyio
async def test_logout_revokes_current_refresh_token(async_client):
    payload = {"email": unique_email(), "password": "secret123"}
    login_response = await async_client.post("/auth/register", json=payload)
    refresh_token = login_response.json()["refresh_token"]

    logout_response = await async_client.post(
        "/auth/logout", json={"refresh_token": refresh_token}
    )
    assert logout_response.status_code == 204

    refresh_response = await async_client.post(
        "/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert refresh_response.status_code == 401


@pytest.mark.anyio
async def test_logout_all_revokes_user_active_refresh_tokens(async_client):
    payload = {"email": unique_email(), "password": "secret123"}
    login_response = await async_client.post("/auth/register", json=payload)
    data = login_response.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]

    logout_all_response = await async_client.post(
        "/auth/logout-all",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert logout_all_response.status_code == 204

    refresh_response = await async_client.post(
        "/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert refresh_response.status_code == 401


@pytest.mark.anyio
async def test_login_rate_limit(async_client, monkeypatch):
    payload = {"email": unique_email(), "password": "secret123"}
    await async_client.post("/auth/register", json=payload)

    auth_router._rate_limiter_buckets.clear()
    monkeypatch.setattr(auth_router, "LOGIN_RATE_LIMIT_MAX", 1)
    monkeypatch.setattr(auth_router, "LOGIN_RATE_LIMIT_WINDOW_SECONDS", 60)

    first = await async_client.post("/auth/login", json=payload)
    second = await async_client.post("/auth/login", json=payload)

    assert first.status_code == 200
    assert second.status_code == 429


@pytest.mark.anyio
async def test_refresh_rate_limit(async_client, monkeypatch):
    payload = {"email": unique_email(), "password": "secret123"}
    register_response = await async_client.post("/auth/register", json=payload)
    refresh_token = register_response.json()["refresh_token"]

    auth_router._rate_limiter_buckets.clear()
    monkeypatch.setattr(auth_router, "REFRESH_RATE_LIMIT_MAX", 1)
    monkeypatch.setattr(auth_router, "REFRESH_RATE_LIMIT_WINDOW_SECONDS", 60)

    first = await async_client.post(
        "/auth/refresh", json={"refresh_token": refresh_token}
    )
    second = await async_client.post(
        "/auth/refresh", json={"refresh_token": first.json()["refresh_token"]}
    )

    assert first.status_code == 200
    assert second.status_code == 429


@pytest.mark.anyio
async def test_refresh_reuse_writes_audit_event(async_client):
    auth_router._rate_limiter_buckets.clear()
    payload = {"email": unique_email(), "password": "secret123"}
    register_response = await async_client.post("/auth/register", json=payload)
    original_refresh = register_response.json()["refresh_token"]

    rotated = await async_client.post(
        "/auth/refresh", json={"refresh_token": original_refresh}
    )
    assert rotated.status_code == 200

    reuse = await async_client.post(
        "/auth/refresh", json={"refresh_token": original_refresh}
    )
    assert reuse.status_code == 401

    event = await database.fetch_one(
        auth_security_event_table.select()
        .where(auth_security_event_table.c.event_type == "refresh_reuse_detected")
        .order_by(auth_security_event_table.c.id.desc())
    )
    assert event is not None
