from dataclasses import dataclass
from functools import lru_cache
import os

from dotenv import load_dotenv

load_dotenv()


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    env_state: str
    database_url: str
    db_force_rollback: bool = False
    auth_secret: str = "dev-secret"
    access_token_exp_minutes: int = 15
    refresh_token_exp_days: int = 30
    login_rate_limit_max: int = 10
    login_rate_limit_window_seconds: int = 60
    refresh_rate_limit_max: int = 30
    refresh_rate_limit_window_seconds: int = 60
    upload_dir: str = "uploads/images"
    upload_url_prefix: str = "/uploads/images"
    max_image_upload_bytes: int = 5 * 1024 * 1024
    firebase_service_account_path: str | None = None


@lru_cache()
def get_config() -> Settings:
    env_state = os.getenv("ENV_STATE", "dev").strip().lower()
    env_prefix = {"dev": "DEV_", "prod": "PROD_", "test": "TEST_"}.get(env_state, "")

    # Prefer prefixed variables by environment, with generic fallbacks.
    database_url = os.getenv(f"{env_prefix}DATABASE_URL") or os.getenv("DATABASE_URL")
    if not database_url and env_state == "test":
        database_url = os.getenv("DEV_DATABASE_URL")

    if not database_url:
        raise ValueError(
            "DATABASE_URL is not set. Provide DATABASE_URL or an env-specific "
            "value like DEV_DATABASE_URL in your .env file."
        )

    db_force_rollback = _as_bool(
        os.getenv(f"{env_prefix}DB_FORCE_ROLL_BACK") or os.getenv("DB_FORCE_ROLL_BACK"),
        default=False,
    )

    auth_secret = os.getenv(f"{env_prefix}AUTH_SECRET") or os.getenv(
        "AUTH_SECRET", "dev-secret"
    )
    access_token_exp_minutes = int(
        os.getenv(f"{env_prefix}ACCESS_TOKEN_EXP_MINUTES")
        or os.getenv("ACCESS_TOKEN_EXP_MINUTES")
        or os.getenv(f"{env_prefix}AUTH_TOKEN_EXP_MINUTES")
        or os.getenv("AUTH_TOKEN_EXP_MINUTES", "15")
    )
    refresh_token_exp_days = int(
        os.getenv(f"{env_prefix}REFRESH_TOKEN_EXP_DAYS")
        or os.getenv("REFRESH_TOKEN_EXP_DAYS", "30")
    )
    login_rate_limit_max = int(
        os.getenv(f"{env_prefix}LOGIN_RATE_LIMIT_MAX")
        or os.getenv("LOGIN_RATE_LIMIT_MAX", "10")
    )
    login_rate_limit_window_seconds = int(
        os.getenv(f"{env_prefix}LOGIN_RATE_LIMIT_WINDOW_SECONDS")
        or os.getenv("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "60")
    )
    refresh_rate_limit_max = int(
        os.getenv(f"{env_prefix}REFRESH_RATE_LIMIT_MAX")
        or os.getenv("REFRESH_RATE_LIMIT_MAX", "30")
    )
    refresh_rate_limit_window_seconds = int(
        os.getenv(f"{env_prefix}REFRESH_RATE_LIMIT_WINDOW_SECONDS")
        or os.getenv("REFRESH_RATE_LIMIT_WINDOW_SECONDS", "60")
    )
    upload_dir = os.getenv(f"{env_prefix}UPLOAD_DIR") or os.getenv(
        "UPLOAD_DIR", "uploads/images"
    )
    upload_url_prefix = os.getenv(f"{env_prefix}UPLOAD_URL_PREFIX") or os.getenv(
        "UPLOAD_URL_PREFIX", "/uploads/images"
    )
    max_image_upload_bytes = int(
        os.getenv(f"{env_prefix}MAX_IMAGE_UPLOAD_BYTES")
        or os.getenv("MAX_IMAGE_UPLOAD_BYTES", str(5 * 1024 * 1024))
    )
    firebase_service_account_path = os.getenv(
        f"{env_prefix}FIREBASE_SERVICE_ACCOUNT_PATH"
    ) or os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH")

    if env_state == "test":
        db_force_rollback = True
        auth_secret = os.getenv("TEST_AUTH_SECRET", auth_secret)

    return Settings(
        env_state=env_state,
        database_url=database_url,
        db_force_rollback=db_force_rollback,
        auth_secret=auth_secret,
        access_token_exp_minutes=access_token_exp_minutes,
        refresh_token_exp_days=refresh_token_exp_days,
        login_rate_limit_max=login_rate_limit_max,
        login_rate_limit_window_seconds=login_rate_limit_window_seconds,
        refresh_rate_limit_max=refresh_rate_limit_max,
        refresh_rate_limit_window_seconds=refresh_rate_limit_window_seconds,
        upload_dir=upload_dir,
        upload_url_prefix=upload_url_prefix,
        max_image_upload_bytes=max_image_upload_bytes,
        firebase_service_account_path=firebase_service_account_path,
    )


config = get_config()
