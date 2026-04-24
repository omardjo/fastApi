import asyncio
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
import sqlalchemy

from blogapi.config import config
from blogapi.database import (
    auth_security_event_table,
    database,
    refresh_token_table,
    user_table,
)
from blogapi.models.auth import (
    AuthResponse,
    LogoutRequest,
    RefreshTokenRequest,
    UserCreate,
    UserLogin,
)
from blogapi.security import (
    access_token_expires_in_seconds,
    create_access_token,
    create_refresh_token,
    get_current_user,
    hash_password,
    hash_refresh_token,
    verify_password,
)


router = APIRouter(prefix="/auth", tags=["auth"])
_auth_schema_ready = False
CurrentUser = Annotated[dict, Depends(get_current_user)]
_rate_limiter_lock = asyncio.Lock()
_rate_limiter_buckets: dict[str, deque[float]] = defaultdict(deque)
LOGIN_RATE_LIMIT_MAX = config.login_rate_limit_max
LOGIN_RATE_LIMIT_WINDOW_SECONDS = config.login_rate_limit_window_seconds
REFRESH_RATE_LIMIT_MAX = config.refresh_rate_limit_max
REFRESH_RATE_LIMIT_WINDOW_SECONDS = config.refresh_rate_limit_window_seconds


async def _ensure_auth_schema() -> None:
    global _auth_schema_ready
    if _auth_schema_ready:
        return

    # Runtime-safe migration for legacy databases.
    await database.execute(
        sqlalchemy.text("ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(255)")
    )
    await database.execute(
        sqlalchemy.text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()"
        )
    )
    await database.execute(
        sqlalchemy.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'users' AND column_name = 'username'
                ) THEN
                    UPDATE users
                    SET email = username || '@legacy.local'
                    WHERE email IS NULL;
                END IF;
            END
            $$;
            """
        )
    )
    await database.execute(
        sqlalchemy.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'users' AND column_name = 'username' AND is_nullable = 'NO'
                ) THEN
                    ALTER TABLE users ALTER COLUMN username DROP NOT NULL;
                END IF;
            END
            $$;
            """
        )
    )
    await database.execute(
        sqlalchemy.text("ALTER TABLE users ALTER COLUMN email SET NOT NULL")
    )
    await database.execute(
        sqlalchemy.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email)"
        )
    )
    await database.execute(
        sqlalchemy.text(
            """
            CREATE TABLE IF NOT EXISTS refresh_tokens (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token_hash VARCHAR(128) NOT NULL UNIQUE,
                expires_at TIMESTAMPTZ NOT NULL,
                revoked_at TIMESTAMPTZ NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                replaced_by_token_id INTEGER NULL REFERENCES refresh_tokens(id) ON DELETE SET NULL,
                ip_address VARCHAR(64) NULL,
                user_agent VARCHAR(512) NULL,
                device_id VARCHAR(128) NULL
            )
            """
        )
    )
    await database.execute(
        sqlalchemy.text(
            "ALTER TABLE refresh_tokens ADD COLUMN IF NOT EXISTS ip_address VARCHAR(64)"
        )
    )
    await database.execute(
        sqlalchemy.text(
            "ALTER TABLE refresh_tokens ADD COLUMN IF NOT EXISTS user_agent VARCHAR(512)"
        )
    )
    await database.execute(
        sqlalchemy.text(
            "ALTER TABLE refresh_tokens ADD COLUMN IF NOT EXISTS device_id VARCHAR(128)"
        )
    )
    await database.execute(
        sqlalchemy.text(
            "CREATE INDEX IF NOT EXISTS ix_refresh_tokens_user_id ON refresh_tokens (user_id)"
        )
    )
    await database.execute(
        sqlalchemy.text(
            """
            CREATE TABLE IF NOT EXISTS auth_security_events (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
                event_type VARCHAR(64) NOT NULL,
                ip_address VARCHAR(64) NULL,
                user_agent VARCHAR(512) NULL,
                device_id VARCHAR(128) NULL,
                token_id INTEGER NULL,
                details JSONB NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )
    await database.execute(
        sqlalchemy.text(
            "CREATE INDEX IF NOT EXISTS ix_auth_security_events_user_id ON auth_security_events (user_id)"
        )
    )
    await database.execute(
        sqlalchemy.text(
            "CREATE INDEX IF NOT EXISTS ix_auth_security_events_event_type ON auth_security_events (event_type)"
        )
    )

    _auth_schema_ready = True


def _auth_response(user_id: int, email: str, access_token: str, refresh_token: str):
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": access_token_expires_in_seconds(),
        "user": {"id": user_id, "email": email},
    }


def _extract_session_metadata(request: Request) -> dict:
    x_forwarded_for = request.headers.get("x-forwarded-for", "")
    ip_address = x_forwarded_for.split(",", 1)[0].strip() or (
        request.client.host if request.client else None
    )
    user_agent = request.headers.get("user-agent")
    device_id = request.headers.get("x-device-id")
    return {
        "ip_address": ip_address[:64] if ip_address else None,
        "user_agent": user_agent[:512] if user_agent else None,
        "device_id": device_id[:128] if device_id else None,
    }


def _client_rate_key(request: Request, email: str | None = None) -> str:
    session_meta = _extract_session_metadata(request)
    ip = session_meta.get("ip_address") or "unknown"
    if email:
        return f"{ip}:{email.lower()}"
    return ip


async def _check_rate_limit(
    bucket: str,
    key: str,
    limit: int,
    window_seconds: int,
) -> None:
    now_ts = datetime.now(UTC).timestamp()
    bucket_key = f"{bucket}:{key}"
    async with _rate_limiter_lock:
        hits = _rate_limiter_buckets[bucket_key]
        cutoff = now_ts - window_seconds
        while hits and hits[0] < cutoff:
            hits.popleft()

        if len(hits) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests",
            )

        hits.append(now_ts)


async def _write_security_event(
    event_type: str,
    session_meta: dict,
    user_id: int | None = None,
    token_id: int | None = None,
    details: dict | None = None,
) -> None:
    await database.execute(
        auth_security_event_table.insert().values(
            user_id=user_id,
            event_type=event_type,
            ip_address=session_meta.get("ip_address"),
            user_agent=session_meta.get("user_agent"),
            device_id=session_meta.get("device_id"),
            token_id=token_id,
            details=details,
            created_at=datetime.now(UTC),
        )
    )


async def _is_legacy_username_required() -> bool:
    row = await database.fetch_one(
        sqlalchemy.text(
            """
            SELECT is_nullable
            FROM information_schema.columns
            WHERE table_name = 'users' AND column_name = 'username'
            LIMIT 1
            """
        )
    )
    return row is not None and row["is_nullable"] == "NO"


async def _persist_refresh_token(
    user_id: int,
    refresh_token: str,
    session_meta: dict,
    replaced_token_id: int | None = None,
) -> int:
    now = datetime.now(UTC)
    expires_at = now + timedelta(days=config.refresh_token_exp_days)
    refresh_token_id = await database.execute(
        refresh_token_table.insert().values(
            user_id=user_id,
            token_hash=hash_refresh_token(refresh_token),
            created_at=now,
            expires_at=expires_at,
            ip_address=session_meta.get("ip_address"),
            user_agent=session_meta.get("user_agent"),
            device_id=session_meta.get("device_id"),
        )
    )

    if replaced_token_id is not None:
        await database.execute(
            refresh_token_table.update()
            .where(refresh_token_table.c.id == replaced_token_id)
            .values(revoked_at=now, replaced_by_token_id=refresh_token_id)
        )

    return refresh_token_id


async def _issue_token_pair(
    user_id: int,
    email: str,
    session_meta: dict,
    replaced_token_id: int | None = None,
):
    access_token = create_access_token(user_id, email)
    refresh_token = create_refresh_token()
    await _persist_refresh_token(
        user_id=user_id,
        refresh_token=refresh_token,
        session_meta=session_meta,
        replaced_token_id=replaced_token_id,
    )
    return _auth_response(user_id, email, access_token, refresh_token)


async def _revoke_active_refresh_tokens_for_user(user_id: int) -> None:
    now = datetime.now(UTC)
    await database.execute(
        refresh_token_table.update()
        .where(
            (refresh_token_table.c.user_id == user_id)
            & (refresh_token_table.c.revoked_at.is_(None))
        )
        .values(revoked_at=now)
    )


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(user: UserCreate, request: Request):
    await _ensure_auth_schema()
    existing_query = user_table.select().where(user_table.c.email == user.email)
    existing_user = await database.fetch_one(existing_query)
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already exists"
        )

    data = {
        "email": user.email,
        "password_hash": hash_password(user.password),
    }
    if await _is_legacy_username_required():
        data["username"] = user.email
    user_id = await database.execute(user_table.insert().values(data))
    return await _issue_token_pair(
        user_id=user_id,
        email=user.email,
        session_meta=_extract_session_metadata(request),
    )


@router.post("/login", response_model=AuthResponse)
async def login(user: UserLogin, request: Request):
    await _ensure_auth_schema()
    await _check_rate_limit(
        bucket="login",
        key=_client_rate_key(request, user.email),
        limit=LOGIN_RATE_LIMIT_MAX,
        window_seconds=LOGIN_RATE_LIMIT_WINDOW_SECONDS,
    )
    query = user_table.select().where(user_table.c.email == user.email)
    existing_user = await database.fetch_one(query)
    if existing_user is None or not verify_password(
        user.password, existing_user["password_hash"]
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )

    return await _issue_token_pair(
        user_id=existing_user["id"],
        email=existing_user["email"],
        session_meta=_extract_session_metadata(request),
    )


@router.post("/refresh", response_model=AuthResponse)
async def refresh_tokens(payload: RefreshTokenRequest, request: Request):
    await _ensure_auth_schema()
    session_meta = _extract_session_metadata(request)
    await _check_rate_limit(
        bucket="refresh",
        key=_client_rate_key(request),
        limit=REFRESH_RATE_LIMIT_MAX,
        window_seconds=REFRESH_RATE_LIMIT_WINDOW_SECONDS,
    )
    token_hash = hash_refresh_token(payload.refresh_token)
    query = refresh_token_table.select().where(
        refresh_token_table.c.token_hash == token_hash
    )
    existing_token = await database.fetch_one(query)

    if existing_token is None:
        await _write_security_event(
            event_type="refresh_invalid_token",
            session_meta=session_meta,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    user_id = existing_token["user_id"]

    if existing_token["revoked_at"] is not None:
        # Reuse of an already rotated/revoked refresh token is a compromise signal.
        await _write_security_event(
            event_type="refresh_reuse_detected",
            session_meta=session_meta,
            user_id=user_id,
            token_id=existing_token["id"],
            details={"reason": "revoked_token_reuse"},
        )
        await _revoke_active_refresh_tokens_for_user(user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked",
        )

    if existing_token["expires_at"] <= datetime.now(UTC):
        await _write_security_event(
            event_type="refresh_expired_token",
            session_meta=session_meta,
            user_id=user_id,
            token_id=existing_token["id"],
        )
        await database.execute(
            refresh_token_table.update()
            .where(refresh_token_table.c.id == existing_token["id"])
            .values(revoked_at=datetime.now(UTC))
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired",
        )

    user = await database.fetch_one(
        user_table.select().where(user_table.c.id == existing_token["user_id"])
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    async with database.transaction():
        return await _issue_token_pair(
            user_id=user["id"],
            email=user["email"],
            session_meta=session_meta,
            replaced_token_id=existing_token["id"],
        )


@router.post("/logout", status_code=204)
async def logout(payload: LogoutRequest) -> Response:
    await _ensure_auth_schema()
    token_hash = hash_refresh_token(payload.refresh_token)
    existing_token = await database.fetch_one(
        refresh_token_table.select().where(
            refresh_token_table.c.token_hash == token_hash
        )
    )

    if existing_token is not None and existing_token["revoked_at"] is None:
        await database.execute(
            refresh_token_table.update()
            .where(refresh_token_table.c.id == existing_token["id"])
            .values(revoked_at=datetime.now(UTC))
        )

    return Response(status_code=204)


@router.post("/logout-all", status_code=204)
async def logout_all(current_user: CurrentUser) -> Response:
    await _ensure_auth_schema()
    await _revoke_active_refresh_tokens_for_user(current_user["id"])
    return Response(status_code=204)
