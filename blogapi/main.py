from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from blogapi.config import config
from blogapi.database import database, init_models
from blogapi.routers.auth import router as auth_router
from blogapi.routers.health import router as health_router
from blogapi.routers.me import router as me_router
from blogapi.routers.post import router as post_router
from blogapi.routers.uploads import router as uploads_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_models()
    await database.connect()
    yield  # this yield in summarized way means that the code before it will run before the application starts, and the code after it will run after the application stops.
    await database.disconnect()


app = FastAPI(lifespan=lifespan)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


app.include_router(auth_router)
app.include_router(post_router)
app.include_router(me_router)
app.include_router(uploads_router)
app.include_router(health_router)

upload_dir = Path(config.upload_dir)
if not upload_dir.is_absolute():
    upload_dir = Path.cwd() / upload_dir
upload_dir.mkdir(parents=True, exist_ok=True)
app.mount(config.upload_url_prefix, StaticFiles(directory=upload_dir), name="uploads")
