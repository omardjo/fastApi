import logging
from pathlib import Path
from typing import Any

from sqlalchemy import select

from blogapi.config import config
from blogapi.database import (
    database,
    user_device_token_table,
    user_follow_table,
    user_table,
)

logger = logging.getLogger(__name__)

try:
    import firebase_admin
    from firebase_admin import credentials, messaging
except ImportError:
    firebase_admin = None
    credentials = None
    messaging = None

_firebase_checked = False
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _normalize_data(data: dict[str, Any] | None) -> dict[str, str]:
    if not data:
        return {}
    return {str(key): str(value) for key, value in data.items() if value is not None}


def _service_account_path(value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _firebase_status() -> dict[str, Any]:
    global _firebase_checked
    if firebase_admin is None or credentials is None:
        if not _firebase_checked:
            logger.warning(
                "firebase-admin is not installed; FCM notifications will be skipped"
            )
            _firebase_checked = True
        return {"ready": False, "reason": "firebase_admin_unavailable"}

    if firebase_admin._apps:
        return {"ready": True, "reason": None}

    service_account_path = config.firebase_service_account_path
    if not service_account_path:
        if not _firebase_checked:
            logger.warning(
                "FIREBASE_SERVICE_ACCOUNT_PATH is not configured; FCM notifications will be skipped"
            )
            _firebase_checked = True
        return {"ready": False, "reason": "missing_service_account_path"}

    path = _service_account_path(service_account_path)
    if not path.exists():
        if not _firebase_checked:
            logger.warning(
                "Firebase service account file does not exist at %s; FCM notifications will be skipped",
                path,
            )
            _firebase_checked = True
        return {"ready": False, "reason": "service_account_not_found"}

    try:
        firebase_admin.initialize_app(credentials.Certificate(str(path)))
    except Exception:
        logger.exception("Failed to initialize Firebase Admin SDK")
        _firebase_checked = True
        return {"ready": False, "reason": "firebase_initialization_failed"}

    _firebase_checked = True
    return {"ready": True, "reason": None}


async def send_push_notification(
    token: str,
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
) -> dict:
    status = _firebase_status()
    if not status["ready"]:
        return {
            "sent": False,
            "reason": status["reason"],
            "firebase_configured": False,
        }

    try:
        message_id = messaging.send(
            messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                token=token,
                data=_normalize_data(data),
            )
        )
    except Exception:
        logger.exception("Failed to send FCM notification")
        return {
            "sent": False,
            "reason": "send_failed",
            "firebase_configured": True,
        }

    return {"sent": True, "message_id": message_id, "firebase_configured": True}


async def notify_followers_about_new_post(
    author_id: int, post_id: int, post_title: str
) -> dict:
    author = await database.fetch_one(
        user_table.select().where(user_table.c.id == author_id)
    )
    if author is None:
        logger.warning("Skipping new post notification; author %s not found", author_id)
        return {"sent": 0, "skipped": 0}

    token_query = (
        select(user_device_token_table.c.fcm_token)
        .select_from(
            user_follow_table.join(
                user_device_token_table,
                user_follow_table.c.follower_id == user_device_token_table.c.user_id,
            )
        )
        .where(user_follow_table.c.following_id == author_id)
        .where(user_device_token_table.c.is_active.is_(True))
    )
    rows = await database.fetch_all(token_query)
    tokens = list(dict.fromkeys(row["fcm_token"] for row in rows))
    if not tokens:
        return {"sent": 0, "skipped": 0}

    author_name = author["display_name"] or author["username"] or author["email"]
    data = {
        "type": "new_post",
        "post_id": post_id,
        "author_id": author_id,
        "route": f"/posts/{post_id}",
    }
    sent = 0
    skipped = 0
    for token in tokens:
        result = await send_push_notification(
            token=token,
            title=f"New article from {author_name}",
            body=post_title,
            data=data,
        )
        if result.get("sent"):
            sent += 1
        else:
            skipped += 1

    return {"sent": sent, "skipped": skipped}
