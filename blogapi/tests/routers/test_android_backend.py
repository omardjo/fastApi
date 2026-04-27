from uuid import uuid4

from httpx import AsyncClient
import pytest

from blogapi.config import config

IMAGE_FIXTURES = {
    "image/jpeg": b"\xff\xd8\xff\xe0jpeg",
    "image/png": b"\x89PNG\r\n\x1a\npng",
    "image/webp": b"RIFF\x04\x00\x00\x00WEBPwebp",
    "image/gif": b"GIF89agif",
}


async def register_user(async_client: AsyncClient) -> dict:
    email = f"android-{uuid4().hex}@example.com"
    response = await async_client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "secret123",
            "username": f"u_{uuid4().hex[:8]}",
        },
    )
    assert response.status_code == 201
    data = response.json()
    data["headers"] = {"Authorization": f"Bearer {data['access_token']}"}
    return data


async def upload_image(
    async_client: AsyncClient,
    headers: dict[str, str],
    original_name: str,
    content_type: str,
) -> dict:
    response = await async_client.post(
        "/uploads/images",
        headers=headers,
        files={"file": (original_name, IMAGE_FIXTURES[content_type], content_type)},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["url"] == f"/uploads/images/{data['filename']}"
    assert data["url"].startswith("/uploads/images/")
    assert data["filename"] not in {original_name, original_name.rsplit(".", 1)[0]}
    assert data["content_type"] == content_type
    assert data["size"] == len(IMAGE_FIXTURES[content_type])
    return data


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("original_name", "content_type", "expected_extension"),
    [
        ("avatar.jpg", "image/jpeg", ".jpg"),
        ("avatar.jpeg", "image/jpeg", ".jpg"),
        ("avatar.png", "image/png", ".png"),
        ("avatar.webp", "image/webp", ".webp"),
        ("avatar.gif", "image/gif", ".gif"),
    ],
)
async def test_image_upload_accepts_supported_types_and_serves_static_file(
    async_client: AsyncClient,
    original_name: str,
    content_type: str,
    expected_extension: str,
):
    user = await register_user(async_client)

    uploaded = await upload_image(
        async_client, user["headers"], original_name, content_type
    )

    assert uploaded["filename"].endswith(expected_extension)
    static_response = await async_client.get(uploaded["url"])
    assert static_response.status_code == 200
    assert static_response.content == IMAGE_FIXTURES[content_type]


@pytest.mark.anyio
async def test_image_upload_rejects_unsupported_type_mismatched_body_and_large_file(
    async_client: AsyncClient,
):
    user = await register_user(async_client)
    headers = user["headers"]

    unsupported = await async_client.post(
        "/uploads/images",
        headers=headers,
        files={"file": ("avatar.txt", b"plain text", "text/plain")},
    )
    assert unsupported.status_code == 415

    mismatched = await async_client.post(
        "/uploads/images",
        headers=headers,
        files={"file": ("avatar.png", b"not a png", "image/png")},
    )
    assert mismatched.status_code == 400

    too_large = await async_client.post(
        "/uploads/images",
        headers=headers,
        files={
            "file": (
                "avatar.png",
                IMAGE_FIXTURES["image/png"] + (b"x" * config.max_image_upload_bytes),
                "image/png",
            )
        },
    )
    assert too_large.status_code == 413


@pytest.mark.anyio
async def test_android_upload_avatar_then_update_and_fetch_profile(
    async_client: AsyncClient,
):
    user = await register_user(async_client)
    headers = user["headers"]
    uploaded = await upload_image(
        async_client, headers, "typed-avatar.png", "image/png"
    )

    updated_me = await async_client.put(
        "/auth/me",
        headers=headers,
        json={"avatar_url": uploaded["url"]},
    )
    assert updated_me.status_code == 200
    assert updated_me.json()["avatar_url"] == uploaded["url"]

    fetched_me = await async_client.get("/auth/me", headers=headers)
    assert fetched_me.status_code == 200
    assert fetched_me.json()["avatar_url"] == uploaded["url"]


@pytest.mark.anyio
async def test_android_upload_cover_and_thumbnail_then_create_and_fetch_post(
    async_client: AsyncClient,
):
    user = await register_user(async_client)
    headers = user["headers"]
    cover = await upload_image(async_client, headers, "manual-cover.jpg", "image/jpeg")
    thumbnail = await upload_image(
        async_client, headers, "manual-thumbnail.webp", "image/webp"
    )

    category_slug = f"image-flow-{uuid4().hex[:8]}"
    category = await async_client.post(
        "/categories",
        headers=headers,
        json={"name": f"Image Flow {uuid4().hex[:8]}", "slug": category_slug},
    )
    assert category.status_code == 201

    created_post = await async_client.post(
        "/posts",
        headers=headers,
        json={
            "title": "Android Image Post",
            "content": "Image upload synchronization content.",
            "category_id": category.json()["id"],
            "status": "published",
            "cover_image_url": cover["url"],
            "thumbnail_url": thumbnail["url"],
        },
    )
    assert created_post.status_code == 201
    post = created_post.json()
    assert post["cover_image_url"] == cover["url"]
    assert post["thumbnail_url"] == thumbnail["url"]

    listed = await async_client.get("/posts", headers=headers)
    assert listed.status_code == 200
    listed_post = next(item for item in listed.json() if item["id"] == post["id"])
    assert listed_post["cover_image_url"] == cover["url"]
    assert listed_post["thumbnail_url"] == thumbnail["url"]

    fetched = await async_client.get(f"/posts/{post['id']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["cover_image_url"] == cover["url"]
    assert fetched.json()["thumbnail_url"] == thumbnail["url"]


@pytest.mark.anyio
async def test_android_upload_images_then_update_post_urls(async_client: AsyncClient):
    user = await register_user(async_client)
    headers = user["headers"]
    initial_cover = await upload_image(
        async_client, headers, "initial-cover.gif", "image/gif"
    )
    updated_cover = await upload_image(
        async_client, headers, "updated-cover.png", "image/png"
    )
    updated_thumbnail = await upload_image(
        async_client, headers, "updated-thumbnail.jpeg", "image/jpeg"
    )

    category = await async_client.post(
        "/categories",
        headers=headers,
        json={
            "name": f"Post Update {uuid4().hex[:8]}",
            "slug": f"post-update-{uuid4().hex[:8]}",
        },
    )
    assert category.status_code == 201

    created_post = await async_client.post(
        "/posts",
        headers=headers,
        json={
            "title": "Post Image Update",
            "content": "Initial image content.",
            "category_id": category.json()["id"],
            "cover_image_url": initial_cover["url"],
        },
    )
    assert created_post.status_code == 201

    updated_post = await async_client.put(
        f"/posts/{created_post.json()['id']}",
        headers=headers,
        json={
            "cover_image_url": updated_cover["url"],
            "thumbnail_url": updated_thumbnail["url"],
        },
    )
    assert updated_post.status_code == 200
    assert updated_post.json()["cover_image_url"] == updated_cover["url"]
    assert updated_post.json()["thumbnail_url"] == updated_thumbnail["url"]


@pytest.mark.anyio
async def test_android_profile_posts_saved_activity_and_settings(
    async_client: AsyncClient,
):
    user = await register_user(async_client)
    headers = user["headers"]

    me = await async_client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["saved_posts_count"] == 0

    updated_me = await async_client.put(
        "/auth/me",
        headers=headers,
        json={"display_name": "Riwaq Writer", "bio": "Reads and writes."},
    )
    assert updated_me.status_code == 200
    assert updated_me.json()["display_name"] == "Riwaq Writer"

    upload = await async_client.post(
        "/uploads/images",
        headers=headers,
        files={"file": ("cover.png", IMAGE_FIXTURES["image/png"], "image/png")},
    )
    assert upload.status_code == 201
    cover_url = upload.json()["url"]

    category_slug = f"mobile-{uuid4().hex[:8]}"
    category = await async_client.post(
        "/categories",
        headers=headers,
        json={"name": f"Mobile {uuid4().hex[:8]}", "slug": category_slug},
    )
    assert category.status_code == 201
    category_id = category.json()["id"]
    android_tag_name = f"android-{uuid4().hex[:8]}"

    content = " ".join(["word"] * 401)
    created_post = await async_client.post(
        "/posts",
        headers=headers,
        json={
            "title": "Dynamic Android Post",
            "content": content,
            "category_id": category_id,
            "tags": [android_tag_name, "riwaq"],
            "status": "published",
            "cover_image_url": cover_url,
            "summary": "Server backed summary",
        },
    )
    assert created_post.status_code == 201
    post = created_post.json()
    assert post["cover_image_url"] == cover_url
    assert post["summary"] == "Server backed summary"
    assert post["reading_minutes"] == 3
    assert post["updated_at"]
    post_id = post["id"]

    listed = await async_client.get("/posts", headers=headers)
    assert listed.status_code == 200
    assert any(item["id"] == post_id for item in listed.json())

    other_user = await register_user(async_client)
    forbidden = await async_client.put(
        f"/posts/{post_id}",
        headers=other_user["headers"],
        json={"title": "Nope"},
    )
    assert forbidden.status_code == 403

    comment = await async_client.post(
        f"/posts/{post_id}/comments",
        headers=headers,
        json={"body": "Great read"},
    )
    assert comment.status_code == 201
    assert comment.json()["author"]["display_name"] == "Riwaq Writer"

    saved = await async_client.post(f"/me/saved-posts/{post_id}", headers=headers)
    assert saved.status_code == 201
    assert saved.json()["post"]["id"] == post_id

    saved_list = await async_client.get("/me/saved-posts", headers=headers)
    assert saved_list.status_code == 200
    assert saved_list.json()[0]["post"]["id"] == post_id

    reading_record = await async_client.post(
        f"/me/reading-records/{post_id}",
        headers=headers,
        json={"progress_percent": 100},
    )
    assert reading_record.status_code == 200

    activity = await async_client.get("/me/activity-summary", headers=headers)
    assert activity.status_code == 200
    assert activity.json()["articles_read"] == 1
    assert activity.json()["published_posts"] == 1
    assert activity.json()["saved_posts"] == 1

    categories = await async_client.get(
        "/categories?include_counts=true", headers=headers
    )
    assert categories.status_code == 200
    counted_category = next(
        item for item in categories.json() if item["id"] == category_id
    )
    assert counted_category["posts_count"] == 1

    tags = await async_client.get("/tags?include_counts=true", headers=headers)
    assert tags.status_code == 200
    android_tag = next(item for item in tags.json() if item["name"] == android_tag_name)
    assert android_tag["posts_count"] == 1

    settings = await async_client.put(
        "/me/settings",
        headers=headers,
        json={"notifications_enabled": False, "appearance": "dark", "language": "ar"},
    )
    assert settings.status_code == 200
    assert settings.json()["notifications_enabled"] is False
    assert settings.json()["appearance"] == "dark"


@pytest.mark.anyio
async def test_me_endpoints_require_auth(async_client: AsyncClient):
    response = await async_client.get("/auth/me")
    assert response.status_code == 401

    response = await async_client.get("/me/saved-posts")
    assert response.status_code == 401
