from uuid import uuid4

from httpx import AsyncClient
import pytest

from blogapi.services import firebase_notifications


async def register_user(async_client: AsyncClient, username: str | None = None) -> dict:
    response = await async_client.post(
        "/auth/register",
        json={
            "email": f"follow-{uuid4().hex}@example.com",
            "password": "secret123",
            "username": username or f"u_{uuid4().hex[:8]}",
        },
    )
    assert response.status_code == 201
    data = response.json()
    data["headers"] = {"Authorization": f"Bearer {data['access_token']}"}
    return data


@pytest.mark.anyio
async def test_follow_unfollow_and_status(async_client: AsyncClient):
    suffix = uuid4().hex[:8]
    follower = await register_user(async_client, f"follower_{suffix}")
    author = await register_user(async_client, f"author_{suffix}")
    author_id = author["user"]["id"]

    self_follow = await async_client.post(
        f"/users/{follower['user']['id']}/follow", headers=follower["headers"]
    )
    assert self_follow.status_code == 400

    followed = await async_client.post(
        f"/users/{author_id}/follow", headers=follower["headers"]
    )
    assert followed.status_code == 201
    assert followed.json()["follower_id"] == follower["user"]["id"]
    assert followed.json()["following_id"] == author_id

    duplicate = await async_client.post(
        f"/users/{author_id}/follow", headers=follower["headers"]
    )
    assert duplicate.status_code == 201

    status_response = await async_client.get(
        f"/users/{author_id}/follow-status", headers=follower["headers"]
    )
    assert status_response.status_code == 200
    assert status_response.json() == {"user_id": author_id, "is_following": True}

    followers = await async_client.get(
        f"/users/{author_id}/followers", headers=follower["headers"]
    )
    assert followers.status_code == 200
    assert [user["id"] for user in followers.json()] == [follower["user"]["id"]]

    following = await async_client.get(
        f"/users/{follower['user']['id']}/following", headers=follower["headers"]
    )
    assert following.status_code == 200
    assert [user["id"] for user in following.json()] == [author_id]

    me = await async_client.get("/auth/me", headers=author["headers"])
    assert me.status_code == 200
    assert me.json()["followers_count"] == 1

    unfollowed = await async_client.delete(
        f"/users/{author_id}/follow", headers=follower["headers"]
    )
    assert unfollowed.status_code == 204

    status_response = await async_client.get(
        f"/users/{author_id}/follow-status", headers=follower["headers"]
    )
    assert status_response.status_code == 200
    assert status_response.json()["is_following"] is False


@pytest.mark.anyio
async def test_list_users_is_paginated_and_safe(async_client: AsyncClient):
    user = await register_user(async_client)
    await register_user(async_client)

    response = await async_client.get(
        "/users", headers=user["headers"], params={"page": 1, "limit": 1}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 1
    assert data["limit"] == 1
    assert data["total"] >= 1
    assert len(data["items"]) == 1
    assert "id" in data["items"][0]
    assert "username" in data["items"][0]
    assert "password_hash" not in data["items"][0]
    assert "email" not in data["items"][0]
    assert "role" not in data["items"][0]


@pytest.mark.anyio
async def test_list_users_searches_username_and_email_without_returning_email(
    async_client: AsyncClient,
):
    suffix = uuid4().hex
    username = f"search_{suffix[:8]}"
    user = await register_user(async_client, username)

    username_response = await async_client.get(
        "/users", headers=user["headers"], params={"search": username}
    )
    assert username_response.status_code == 200
    username_items = username_response.json()["items"]
    assert any(item["id"] == user["user"]["id"] for item in username_items)
    assert all("email" not in item for item in username_items)

    email_response = await async_client.get(
        "/users", headers=user["headers"], params={"search": user["user"]["email"]}
    )
    assert email_response.status_code == 200
    email_items = email_response.json()["items"]
    assert any(item["id"] == user["user"]["id"] for item in email_items)
    assert all("email" not in item for item in email_items)


@pytest.mark.anyio
async def test_get_user_public_profile_is_safe_and_includes_follow_state(
    async_client: AsyncClient,
):
    suffix = uuid4().hex[:8]
    follower = await register_user(async_client, f"profile_follower_{suffix}")
    author = await register_user(async_client, f"profile_author_{suffix}")
    author_id = author["user"]["id"]

    await async_client.post(f"/users/{author_id}/follow", headers=follower["headers"])

    response = await async_client.get(f"/users/{author_id}", headers=follower["headers"])
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == author_id
    assert data["username"] == author["user"]["username"]
    assert data["followers_count"] == 1
    assert data["following_count"] == 0
    assert data["is_following"] is True
    assert "email" not in data
    assert "password_hash" not in data
    assert "role" not in data


@pytest.mark.anyio
async def test_users_endpoint_requires_auth(async_client: AsyncClient):
    response = await async_client.get("/users")
    assert response.status_code == 401


@pytest.mark.anyio
async def test_upsert_device_token_moves_token_to_current_user(
    async_client: AsyncClient,
):
    first = await register_user(async_client)
    second = await register_user(async_client)
    token = f"fcm-{uuid4().hex}"

    created = await async_client.put(
        "/me/device-token",
        headers=first["headers"],
        json={"fcm_token": token, "device_name": "Pixel 8"},
    )
    assert created.status_code == 200
    assert created.json()["user_id"] == first["user"]["id"]
    assert created.json()["platform"] == "android"
    assert created.json()["device_name"] == "Pixel 8"
    assert created.json()["is_active"] is True

    updated = await async_client.put(
        "/me/device-token",
        headers=second["headers"],
        json={"fcm_token": token, "platform": "ios", "device_name": "iPhone"},
    )
    assert updated.status_code == 200
    assert updated.json()["id"] == created.json()["id"]
    assert updated.json()["user_id"] == second["user"]["id"]
    assert updated.json()["platform"] == "ios"
    assert updated.json()["device_name"] == "iPhone"


@pytest.mark.anyio
async def test_notification_test_endpoint_is_protected(async_client: AsyncClient):
    response = await async_client.post(
        "/notifications/test",
        json={"token": "token", "title": "Title", "body": "Body"},
    )
    assert response.status_code == 401


@pytest.mark.anyio
async def test_notification_test_endpoint_skips_when_firebase_path_missing(
    async_client: AsyncClient, monkeypatch
):
    user = await register_user(async_client)

    class FirebaseAdminStub:
        _apps = []

    class ConfigStub:
        firebase_service_account_path = None

    monkeypatch.setattr(firebase_notifications, "firebase_admin", FirebaseAdminStub())
    monkeypatch.setattr(firebase_notifications, "credentials", object())
    monkeypatch.setattr(firebase_notifications, "config", ConfigStub())
    monkeypatch.setattr(firebase_notifications, "_firebase_checked", False)

    response = await async_client.post(
        "/notifications/test",
        headers=user["headers"],
        json={"token": "token", "title": "Title", "body": "Body"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "sent": False,
        "message_id": None,
        "reason": "missing_service_account_path",
        "firebase_configured": False,
    }


@pytest.mark.anyio
async def test_firebase_service_account_path_supports_project_relative_paths():
    path = firebase_notifications._service_account_path(
        "secrets/riwaq-firebase-adminsdk.json"
    )
    assert path == (
        firebase_notifications.PROJECT_ROOT
        / "secrets"
        / "riwaq-firebase-adminsdk.json"
    )
