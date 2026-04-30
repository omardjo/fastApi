from datetime import UTC, datetime
from uuid import uuid4

from httpx import AsyncClient
import pytest

from blogapi.config import config
from blogapi.database import database, reading_record_table

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
        json={"notifications_enabled": False, "appearance": "dark", "language": "fr"},
    )
    assert settings.status_code == 200
    assert settings.json()["notifications_enabled"] is False
    assert settings.json()["appearance"] == "dark"
    assert settings.json()["language"] == "fr"


@pytest.mark.anyio
async def test_me_settings_post_persists_partial_updates_and_is_per_user(
    async_client: AsyncClient,
):
    first_user = await register_user(async_client)
    first_headers = first_user["headers"]
    second_user = await register_user(async_client)
    second_headers = second_user["headers"]

    defaults = await async_client.get("/me/settings", headers=first_headers)
    assert defaults.status_code == 200
    assert defaults.json()["notifications_enabled"] is True
    assert defaults.json()["appearance"] == "system"
    assert defaults.json()["language"] == "en"

    updated = await async_client.post(
        "/me/settings",
        headers=first_headers,
        json={
            "notifications_enabled": False,
            "appearance": "dark",
            "language": "fr",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["notifications_enabled"] is False
    assert updated.json()["appearance"] == "dark"
    assert updated.json()["language"] == "fr"
    assert updated.json()["updated_at"] is not None

    partial = await async_client.post(
        "/me/settings",
        headers=first_headers,
        json={"appearance": "light"},
    )
    assert partial.status_code == 200
    assert partial.json()["notifications_enabled"] is False
    assert partial.json()["appearance"] == "light"
    assert partial.json()["language"] == "fr"

    persisted = await async_client.get("/me/settings", headers=first_headers)
    assert persisted.status_code == 200
    assert persisted.json()["notifications_enabled"] is False
    assert persisted.json()["appearance"] == "light"
    assert persisted.json()["language"] == "fr"

    other_user_settings = await async_client.get("/me/settings", headers=second_headers)
    assert other_user_settings.status_code == 200
    assert other_user_settings.json()["notifications_enabled"] is True
    assert other_user_settings.json()["appearance"] == "system"
    assert other_user_settings.json()["language"] == "en"


@pytest.mark.anyio
async def test_me_settings_rejects_invalid_appearance_and_language(
    async_client: AsyncClient,
):
    user = await register_user(async_client)
    headers = user["headers"]

    invalid_appearance = await async_client.post(
        "/me/settings",
        headers=headers,
        json={"appearance": "midnight"},
    )
    assert invalid_appearance.status_code == 422

    invalid_language = await async_client.post(
        "/me/settings",
        headers=headers,
        json={"language": "ar"},
    )
    assert invalid_language.status_code == 422


@pytest.mark.anyio
async def test_android_reading_journey_groups_progress_by_category(
    async_client: AsyncClient,
):
    user = await register_user(async_client)
    headers = user["headers"]

    category = await async_client.post(
        "/categories",
        headers=headers,
        json={
            "name": f"Journey {uuid4().hex[:8]}",
            "slug": f"journey-{uuid4().hex[:8]}",
        },
    )
    assert category.status_code == 201
    category_id = category.json()["id"]

    first = await async_client.post(
        "/posts",
        headers=headers,
        json={
            "title": "Journey Complete",
            "content": " ".join(["complete"] * 260),
            "category_id": category_id,
            "status": "published",
        },
    )
    assert first.status_code == 201
    second = await async_client.post(
        "/posts",
        headers=headers,
        json={
            "title": "Journey Started",
            "content": " ".join(["started"] * 80),
            "category_id": category_id,
            "status": "published",
        },
    )
    assert second.status_code == 201

    first_id = first.json()["id"]
    second_id = second.json()["id"]
    completed = await async_client.post(
        f"/posts/{first_id}/reading-progress",
        headers=headers,
        json={"progress_percent": 100},
    )
    assert completed.status_code == 200
    assert completed.json()["progress_percent"] == 100
    assert completed.json()["completed_at"] is not None

    partial = await async_client.post(
        f"/me/reading-records/{second_id}",
        headers=headers,
        json={"progress_percent": 50, "reading_minutes": 7},
    )
    assert partial.status_code == 200

    saved = await async_client.post(f"/me/saved-posts/{second_id}", headers=headers)
    assert saved.status_code == 201

    response = await async_client.get("/me/reading-journey", headers=headers)
    assert response.status_code == 200
    journey_category = next(
        item
        for item in response.json()["categories"]
        if item["category_id"] == category_id
    )
    assert journey_category["category_name"] == category.json()["name"]
    assert journey_category["total_posts"] == 2
    assert journey_category["started_posts"] == 2
    assert journey_category["completed_posts"] == 1
    assert journey_category["saved_posts"] == 1
    assert journey_category["progress_percent"] == 75
    assert (
        journey_category["reading_minutes"] == completed.json()["reading_minutes"] + 7
    )
    assert journey_category["last_read_at"] is not None
    assert "months" in response.json()


@pytest.mark.anyio
async def test_android_reading_journey_groups_progress_by_month(
    async_client: AsyncClient,
):
    user = await register_user(async_client)
    headers = user["headers"]

    category = await async_client.post(
        "/categories",
        headers=headers,
        json={
            "name": f"Monthly Journey {uuid4().hex[:8]}",
            "slug": f"monthly-journey-{uuid4().hex[:8]}",
        },
    )
    assert category.status_code == 201
    category_id = category.json()["id"]

    first = await async_client.post(
        "/posts",
        headers=headers,
        json={
            "title": "Monthly Complete",
            "content": " ".join(["complete"] * 260),
            "category_id": category_id,
            "status": "published",
        },
    )
    second = await async_client.post(
        "/posts",
        headers=headers,
        json={
            "title": "Monthly Started",
            "content": " ".join(["started"] * 80),
            "category_id": category_id,
            "status": "published",
        },
    )
    assert first.status_code == 201
    assert second.status_code == 201
    first_id = first.json()["id"]
    second_id = second.json()["id"]

    completed = await async_client.post(
        f"/posts/{first_id}/reading-progress",
        headers=headers,
        json={"progress_percent": 100, "reading_minutes": 5},
    )
    partial = await async_client.post(
        f"/posts/{second_id}/reading-progress",
        headers=headers,
        json={"progress_percent": 50, "reading_minutes": 7},
    )
    assert completed.status_code == 200
    assert partial.status_code == 200

    april_completed_at = datetime(2026, 4, 29, 19, 36, 38, tzinfo=UTC)
    april_updated_at = datetime(2026, 4, 29, 19, 30, 0, tzinfo=UTC)
    await database.execute(
        reading_record_table.update()
        .where(reading_record_table.c.post_id == first_id)
        .values(completed_at=april_completed_at, updated_at=april_updated_at)
    )
    await database.execute(
        reading_record_table.update()
        .where(reading_record_table.c.post_id == second_id)
        .values(
            completed_at=None,
            updated_at=datetime(2026, 4, 15, 12, 0, 0, tzinfo=UTC),
        )
    )

    response = await async_client.get("/me/reading-journey", headers=headers)
    assert response.status_code == 200
    months = response.json()["months"]
    april = next(item for item in months if item["year"] == 2026 and item["month"] == 4)

    assert april["month_label"] == "April 2026"
    assert april["started_posts"] == 2
    assert april["completed_posts"] == 1
    assert april["reading_minutes"] == 12
    assert april["progress_percent"] == 75
    assert april["last_read_at"].startswith("2026-04-29T19:36:38")
    month_category = next(
        item for item in april["categories"] if item["category_id"] == category_id
    )
    assert month_category["total_posts"] == 2
    assert month_category["started_posts"] == 2
    assert month_category["completed_posts"] == 1
    assert month_category["progress_percent"] == 75
    assert month_category["reading_minutes"] == 12


@pytest.mark.anyio
async def test_android_reading_journey_months_sort_newest_first(
    async_client: AsyncClient,
):
    user = await register_user(async_client)
    headers = user["headers"]

    category = await async_client.post(
        "/categories",
        headers=headers,
        json={
            "name": f"Sorted Journey {uuid4().hex[:8]}",
            "slug": f"sorted-journey-{uuid4().hex[:8]}",
        },
    )
    assert category.status_code == 201
    category_id = category.json()["id"]

    post_ids = []
    for title in ["March Read", "April Read"]:
        created = await async_client.post(
            "/posts",
            headers=headers,
            json={
                "title": title,
                "content": "Timeline content.",
                "category_id": category_id,
                "status": "published",
            },
        )
        assert created.status_code == 201
        post_ids.append(created.json()["id"])
        progress = await async_client.post(
            f"/posts/{created.json()['id']}/reading-progress",
            headers=headers,
            json={"progress_percent": 100, "reading_minutes": 1},
        )
        assert progress.status_code == 200

    await database.execute(
        reading_record_table.update()
        .where(reading_record_table.c.post_id == post_ids[0])
        .values(
            completed_at=datetime(2026, 3, 10, 10, 0, 0, tzinfo=UTC),
            updated_at=datetime(2026, 3, 10, 10, 0, 0, tzinfo=UTC),
        )
    )
    await database.execute(
        reading_record_table.update()
        .where(reading_record_table.c.post_id == post_ids[1])
        .values(
            completed_at=datetime(2026, 4, 10, 10, 0, 0, tzinfo=UTC),
            updated_at=datetime(2026, 4, 10, 10, 0, 0, tzinfo=UTC),
        )
    )

    response = await async_client.get("/me/reading-journey", headers=headers)
    assert response.status_code == 200
    relevant_months = [
        (item["year"], item["month"])
        for item in response.json()["months"]
        if any(category["category_id"] == category_id for category in item["categories"])
    ]
    assert relevant_months == [(2026, 4), (2026, 3)]


@pytest.mark.anyio
async def test_android_empty_reading_journey_includes_empty_months(
    async_client: AsyncClient,
):
    user = await register_user(async_client)

    response = await async_client.get("/me/reading-journey", headers=user["headers"])
    assert response.status_code == 200
    data = response.json()
    assert "categories" in data
    assert data["months"] == []


@pytest.mark.anyio
async def test_me_endpoints_require_auth(async_client: AsyncClient):
    response = await async_client.get("/auth/me")
    assert response.status_code == 401

    response = await async_client.get("/me/saved-posts")
    assert response.status_code == 401

    response = await async_client.get("/me/reading-journey")
    assert response.status_code == 401

    response = await async_client.post("/me/settings", json={"appearance": "dark"})
    assert response.status_code == 401
