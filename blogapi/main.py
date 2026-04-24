from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from blogapi.database import database, init_models
from blogapi.routers.auth import router as auth_router
from blogapi.routers.health import router as health_router
from blogapi.routers.post import router as post_router


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
app.include_router(health_router)
