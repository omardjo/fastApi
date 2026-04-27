import os
from typing import AsyncGenerator, Generator

import pytest
from fastapi.testclient import (
    TestClient,
)  # allow us to interact with clients API without having to start the FastApi server
from httpx import (
    ASGITransport,
    AsyncClient,
)  # we use it to make the requests to our API

os.environ["ENV_STATE"] = (
    "test"  # we set this environment variable to test so that when we import the config it will use the TestConfig class and populate the environment variables from there. This is important because we want to make sure that when we run our tests we're using the test database and not the development or production database.
)
from blogapi.database import database, engine, init_models  # noqa: E402

from blogapi.main import app  # noqa: E402

# IMPORTS Must be at the top of the file.so adding this comment to ignore that rule.

_schema_initialized = False


@pytest.fixture(scope="session")
def anyio_backend():  # it tells it's async platform when using async functions in our tests
    return "asyncio"  # ensure its runs once per test session


@pytest.fixture()
def client() -> Generator:
    yield TestClient(
        app
    )  # why yield? because sometimes we want to do some setup before and after the test


@pytest.fixture(autouse=True)  # ensure it runs in every test
async def db() -> AsyncGenerator:
    global _schema_initialized
    if not _schema_initialized:
        await init_models()
        await engine.dispose()
        _schema_initialized = True
    await database.connect()
    yield
    await database.disconnect()


@pytest.fixture()
async def async_client(client) -> AsyncGenerator:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url=str(client.base_url)
    ) as ac:
        yield ac
