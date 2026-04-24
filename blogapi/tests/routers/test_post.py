from httpx import AsyncClient
import pytest
from uuid import uuid4


async def auth_headers(async_client: AsyncClient) -> dict[str, str]:
    email = f"writer-{uuid4().hex}@example.com"
    response = await async_client.post(
        "/auth/register", json={"email": email, "password": "secret123"}
    )
    data = response.json()
    return {"Authorization": f"Bearer {data['access_token']}"}


async def create_post(body: str, async_client: AsyncClient) -> dict:
    response = await async_client.post(
        "/post", json={"body": body}, headers=await auth_headers(async_client)
    )
    return response.json()


async def create_comment(body: str, post_id: int, async_client: AsyncClient) -> dict:
    response = await async_client.post(
        "/comment",
        json={"body": body, "post_id": post_id},
        headers=await auth_headers(async_client),
    )
    return response.json()


@pytest.fixture()
async def created_post(async_client: AsyncClient):
    return await create_post("Test Post", async_client)


@pytest.fixture()
async def created_comment(async_client: AsyncClient, created_post: dict):
    return await create_comment("Test Comment", created_post["id"], async_client)


@pytest.mark.anyio
async def test_create_post(async_client: AsyncClient):
    body = "Test Post"
    response = await async_client.post(
        "/post", json={"body": body}, headers=await auth_headers(async_client)
    )
    assert response.status_code == 201
    data = response.json()
    assert data["body"] == body
    assert isinstance(data["id"], int)


@pytest.mark.anyio
async def test_create_post_missing_data(async_client: AsyncClient):
    response = await async_client.post(
        "/post", json={}, headers=await auth_headers(async_client)
    )
    assert response.status_code == 422


@pytest.mark.anyio
async def test_create_post_requires_auth(async_client: AsyncClient):
    response = await async_client.post("/post", json={"body": "Test Post"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


@pytest.mark.anyio
async def test_get_all_posts(async_client: AsyncClient, created_post: dict):
    response = await async_client.get("/post", headers=await auth_headers(async_client))
    assert response.status_code == 200
    assert response.json() == [created_post]


@pytest.mark.anyio
async def test_get_all_posts_requires_auth(async_client: AsyncClient):
    response = await async_client.get("/post")
    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


@pytest.mark.anyio
async def test_create_comment(async_client: AsyncClient, created_post: dict):
    body = "Test Comment"
    response = await async_client.post(
        "/comment",
        json={"body": body, "post_id": created_post["id"]},
        headers=await auth_headers(async_client),
    )
    assert response.status_code == 201
    data = response.json()
    assert data["body"] == body
    assert data["post_id"] == created_post["id"]
    assert isinstance(data["id"], int)


@pytest.mark.anyio
async def test_create_comment_requires_auth(
    async_client: AsyncClient, created_post: dict
):
    response = await async_client.post(
        "/comment", json={"body": "Test Comment", "post_id": created_post["id"]}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


@pytest.mark.anyio
async def test_get_comments_on_post_requires_auth(
    async_client: AsyncClient, created_post: dict
):
    response = await async_client.get(f"/post/{created_post['id']}/comment")
    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


@pytest.mark.anyio
async def test_get_post_with_comments_requires_auth(
    async_client: AsyncClient, created_post: dict
):
    response = await async_client.get(f"/post/{created_post['id']}")
    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"
