import base64
import binascii
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import json
import os
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from blogapi.config import config
from blogapi.database import database, user_table


bearer_scheme = HTTPBearer(auto_error=False)


def _raise_unauthorized(detail: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return f"{salt.hex()}:{digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        salt_hex, digest_hex = password_hash.split(":", 1)
    except ValueError:
        return False

    salt = bytes.fromhex(salt_hex)
    expected = bytes.fromhex(digest_hex)
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return hmac.compare_digest(actual, expected)


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_access_token(user_id: int, email: str) -> str:
    expires_at = datetime.now(UTC) + timedelta(minutes=config.access_token_exp_minutes)
    payload = {
        "sub": str(user_id),
        "email": email,
        "typ": "access",
        "exp": int(expires_at.timestamp()),
    }
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode()
    payload_b64 = _b64encode(payload_bytes)
    signature = hmac.new(
        config.auth_secret.encode(), payload_b64.encode(), hashlib.sha256
    ).digest()
    return f"{payload_b64}.{_b64encode(signature)}"


def decode_access_token(token: str) -> dict:
    try:
        payload_b64, signature_b64 = token.split(".", 1)
    except ValueError:
        _raise_unauthorized("Invalid authentication token")

    expected_signature = hmac.new(
        config.auth_secret.encode(), payload_b64.encode(), hashlib.sha256
    ).digest()
    try:
        actual_signature = _b64decode(signature_b64)
    except (ValueError, binascii.Error):
        _raise_unauthorized("Invalid authentication token")

    if not hmac.compare_digest(actual_signature, expected_signature):
        _raise_unauthorized("Invalid authentication token")

    try:
        payload = json.loads(_b64decode(payload_b64))
    except (ValueError, json.JSONDecodeError, binascii.Error):
        _raise_unauthorized("Invalid authentication token")

    if not isinstance(payload, dict):
        _raise_unauthorized("Invalid authentication token")

    exp = payload.get("exp")
    sub = payload.get("sub")
    token_type = payload.get("typ")

    if not isinstance(exp, int):
        _raise_unauthorized("Invalid authentication token")

    if exp < int(datetime.now(UTC).timestamp()):
        _raise_unauthorized("Authentication token expired")

    if not isinstance(sub, str) or not sub.isdigit():
        _raise_unauthorized("Invalid authentication token")

    if token_type != "access":
        _raise_unauthorized("Invalid authentication token")

    return payload


def access_token_expires_in_seconds() -> int:
    return config.access_token_exp_minutes * 60


def create_refresh_token() -> str:
    # Opaque refresh token stored only on client; backend stores hash only.
    return secrets.token_urlsafe(64)


def hash_refresh_token(refresh_token: str) -> str:
    digest = hmac.new(
        config.auth_secret.encode(), refresh_token.encode(), hashlib.sha256
    ).hexdigest()
    return digest


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
):
    if credentials is None:
        _raise_unauthorized("Authentication required")

    payload = decode_access_token(credentials.credentials)
    query = user_table.select().where(user_table.c.id == int(payload["sub"]))
    user = await database.fetch_one(query)
    if user is None:
        _raise_unauthorized("User not found")
    return user
