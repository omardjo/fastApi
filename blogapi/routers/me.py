import calendar
from collections import defaultdict
from datetime import UTC, date, datetime
import logging
from time import perf_counter
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from blogapi.database import (
    category_table,
    database,
    post_table,
    reading_record_table,
    saved_post_table,
    user_device_token_table,
    user_settings_table,
)
from blogapi.models.me import (
    ActivitySummaryOut,
    ReadingJourneyOut,
    ReadingRecordIn,
    ReadingRecordOut,
    SavedPostOut,
    UserSettingsOut,
    UserSettingsUpdate,
)
from blogapi.models.post import PUBLISHED_STATUS
from blogapi.models.users import DeviceTokenIn, DeviceTokenOut
from blogapi.routers.post import find_post, _post_summary, _reading_minutes
from blogapi.security import get_current_user
from blogapi.services.post_counts import get_user_post_counts

router = APIRouter(prefix="/me", tags=["me"])
CurrentUser = Annotated[dict, Depends(get_current_user)]
logger = logging.getLogger(__name__)


async def _timed_activity_metric(name: str, user_id: int, query):
    started_at = perf_counter()
    try:
        value = await database.fetch_val(query)
    except Exception:
        logger.exception(
            "activity_summary.metric_failed",
            extra={
                "endpoint": "/me/activity-summary",
                "user_id": user_id,
                "metric": name,
                "duration_ms": round((perf_counter() - started_at) * 1000, 2),
            },
        )
        raise

    logger.info(
        "activity_summary.metric_finished",
        extra={
            "endpoint": "/me/activity-summary",
            "user_id": user_id,
            "metric": name,
            "duration_ms": round((perf_counter() - started_at) * 1000, 2),
            "value": value,
        },
    )
    return value


async def _saved_post_out(user_id: int, post_id: int) -> dict:
    saved = await database.fetch_one(
        saved_post_table.select().where(
            (saved_post_table.c.user_id == user_id)
            & (saved_post_table.c.post_id == post_id)
        )
    )
    if saved is None:
        raise HTTPException(status_code=404, detail="Saved post not found")

    post = await find_post(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    return {"post": await _post_summary(post), "saved_at": saved["created_at"]}


@router.get("/saved-posts", response_model=list[SavedPostOut])
async def list_saved_posts(current_user: CurrentUser):
    rows = await database.fetch_all(
        saved_post_table.join(post_table, saved_post_table.c.post_id == post_table.c.id)
        .select()
        .where(saved_post_table.c.user_id == current_user["id"])
        .order_by(saved_post_table.c.created_at.desc())
    )
    result = []
    for row in rows:
        post = await find_post(row["post_id"])
        if post is not None:
            result.append(
                {"post": await _post_summary(post), "saved_at": row["created_at"]}
            )
    return result


@router.post(
    "/saved-posts/{post_id}",
    response_model=SavedPostOut,
    status_code=status.HTTP_201_CREATED,
)
async def save_post(post_id: int, current_user: CurrentUser):
    post = await find_post(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")

    try:
        await database.execute(
            saved_post_table.insert().values(
                user_id=current_user["id"],
                post_id=post_id,
                created_at=datetime.now(UTC),
            )
        )
    except IntegrityError:
        pass
    return await _saved_post_out(current_user["id"], post_id)


@router.delete("/saved-posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unsave_post(post_id: int, current_user: CurrentUser):
    post = await find_post(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")

    existing = await database.fetch_one(
        saved_post_table.select().where(
            (saved_post_table.c.user_id == current_user["id"])
            & (saved_post_table.c.post_id == post_id)
        )
    )
    if existing is None:
        raise HTTPException(status_code=404, detail="Saved post not found")

    await database.execute(
        saved_post_table.delete().where(
            (saved_post_table.c.user_id == current_user["id"])
            & (saved_post_table.c.post_id == post_id)
        )
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/reading-records", response_model=list[ReadingRecordOut])
async def list_reading_records(current_user: CurrentUser):
    rows = await database.fetch_all(
        reading_record_table.select()
        .where(reading_record_table.c.user_id == current_user["id"])
        .order_by(reading_record_table.c.updated_at.desc())
    )
    return [dict(row) for row in rows]


@router.post("/reading-records/{post_id}", response_model=ReadingRecordOut)
async def upsert_reading_record(
    post_id: int, payload: ReadingRecordIn, current_user: CurrentUser
):
    post = await find_post(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")

    now = datetime.now(UTC)
    reading_minutes = payload.reading_minutes
    if reading_minutes is None:
        reading_minutes = _reading_minutes(post["content"] or post["body"])
    completed_at = now if payload.progress_percent >= 100 else None
    existing = await database.fetch_one(
        reading_record_table.select().where(
            (reading_record_table.c.user_id == current_user["id"])
            & (reading_record_table.c.post_id == post_id)
        )
    )
    values = {
        "progress_percent": payload.progress_percent,
        "reading_minutes": reading_minutes,
        "completed_at": completed_at,
        "updated_at": now,
    }
    if existing is None:
        record_id = await database.execute(
            reading_record_table.insert().values(
                user_id=current_user["id"], post_id=post_id, **values
            )
        )
    else:
        record_id = existing["id"]
        if completed_at is None:
            values["completed_at"] = existing["completed_at"]
        await database.execute(
            reading_record_table.update()
            .where(reading_record_table.c.id == record_id)
            .values(**values)
        )

    row = await database.fetch_one(
        reading_record_table.select().where(reading_record_table.c.id == record_id)
    )
    return dict(row)


@router.get("/reading-journey", response_model=ReadingJourneyOut)
async def reading_journey(current_user: CurrentUser):
    categories = await database.fetch_all(
        category_table.select().order_by(category_table.c.name.asc())
    )
    result = []
    category_totals: dict[int, int] = {}
    for category in categories:
        posts_filter = post_table.c.category_id == category["id"]
        published_filter = posts_filter & (
            func.lower(post_table.c.status) == PUBLISHED_STATUS
        )
        total_posts = await database.fetch_val(
            select(func.count()).select_from(post_table).where(published_filter)
        )
        if not total_posts:
            continue
        category_totals[category["id"]] = total_posts

        progress_join = reading_record_table.join(
            post_table, reading_record_table.c.post_id == post_table.c.id
        )
        user_progress_filter = (
            reading_record_table.c.user_id == current_user["id"]
        ) & published_filter
        started_posts = await database.fetch_val(
            select(func.count())
            .select_from(progress_join)
            .where(user_progress_filter & (reading_record_table.c.progress_percent > 0))
        )
        completed_posts = await database.fetch_val(
            select(func.count())
            .select_from(progress_join)
            .where(
                user_progress_filter & (reading_record_table.c.progress_percent >= 100)
            )
        )
        progress_sum = await database.fetch_val(
            select(func.coalesce(func.sum(reading_record_table.c.progress_percent), 0))
            .select_from(progress_join)
            .where(user_progress_filter)
        )
        reading_minutes = await database.fetch_val(
            select(func.coalesce(func.sum(reading_record_table.c.reading_minutes), 0))
            .select_from(progress_join)
            .where(user_progress_filter)
        )
        last_read_at = await database.fetch_val(
            select(func.max(reading_record_table.c.updated_at))
            .select_from(progress_join)
            .where(user_progress_filter)
        )

        saved_join = saved_post_table.join(
            post_table, saved_post_table.c.post_id == post_table.c.id
        )
        saved_posts = await database.fetch_val(
            select(func.count())
            .select_from(saved_join)
            .where(
                (saved_post_table.c.user_id == current_user["id"]) & published_filter
            )
        )
        progress_percent = min(100, round((progress_sum or 0) / total_posts))
        result.append(
            {
                "category_id": category["id"],
                "category_name": category["name"],
                "category_slug": category["slug"],
                "total_posts": total_posts,
                "started_posts": started_posts or 0,
                "completed_posts": completed_posts or 0,
                "saved_posts": saved_posts or 0,
                "progress_percent": progress_percent,
                "reading_minutes": reading_minutes or 0,
                "last_read_at": last_read_at,
            }
        )

    result.sort(key=lambda item: (-item["progress_percent"], item["category_name"]))
    return {
        "categories": result,
        "months": await _reading_journey_months(current_user["id"], category_totals),
    }


def _record_month_at(row) -> datetime | None:
    if row["progress_percent"] >= 100 and row["completed_at"] is not None:
        return row["completed_at"]
    return row["updated_at"]


def _month_key(value: datetime) -> tuple[int, int]:
    return value.year, value.month


def _month_label(year: int, month: int) -> str:
    return f"{calendar.month_name[month]} {year}"


def _empty_month_bucket() -> dict:
    return {
        "started_posts": 0,
        "completed_posts": 0,
        "saved_posts": 0,
        "reading_minutes": 0,
        "progress_sum": 0,
        "last_read_at": None,
        "categories": {},
    }


def _empty_month_category(category_row, total_posts: int) -> dict:
    return {
        "category_id": category_row["category_id"],
        "category_name": category_row["category_name"],
        "category_slug": category_row["category_slug"],
        "total_posts": total_posts,
        "started_posts": 0,
        "completed_posts": 0,
        "saved_posts": 0,
        "progress_sum": 0,
        "reading_minutes": 0,
        "last_read_at": None,
    }


async def _reading_journey_months(user_id: int, category_totals: dict[int, int]):
    progress_join = reading_record_table.join(
        post_table, reading_record_table.c.post_id == post_table.c.id
    ).join(category_table, post_table.c.category_id == category_table.c.id)
    progress_rows = await database.fetch_all(
        select(
            reading_record_table.c.post_id,
            reading_record_table.c.progress_percent,
            reading_record_table.c.reading_minutes,
            reading_record_table.c.completed_at,
            reading_record_table.c.updated_at,
            category_table.c.id.label("category_id"),
            category_table.c.name.label("category_name"),
            category_table.c.slug.label("category_slug"),
        )
        .select_from(progress_join)
        .where(reading_record_table.c.user_id == user_id)
        .where(func.lower(post_table.c.status) == PUBLISHED_STATUS)
        .where(reading_record_table.c.progress_percent > 0)
    )

    saved_join = saved_post_table.join(
        post_table, saved_post_table.c.post_id == post_table.c.id
    ).join(category_table, post_table.c.category_id == category_table.c.id)
    saved_rows = await database.fetch_all(
        select(
            saved_post_table.c.post_id,
            saved_post_table.c.created_at,
            category_table.c.id.label("category_id"),
            category_table.c.name.label("category_name"),
            category_table.c.slug.label("category_slug"),
        )
        .select_from(saved_join)
        .where(saved_post_table.c.user_id == user_id)
        .where(func.lower(post_table.c.status) == PUBLISHED_STATUS)
    )

    months = defaultdict(_empty_month_bucket)

    for row in progress_rows:
        month_at = _record_month_at(row)
        if month_at is None:
            continue
        key = _month_key(month_at)
        month_bucket = months[key]
        category_id = row["category_id"]
        total_posts = category_totals.get(category_id, 0)
        category_bucket = month_bucket["categories"].setdefault(
            category_id, _empty_month_category(row, total_posts)
        )

        month_bucket["started_posts"] += 1
        category_bucket["started_posts"] += 1
        if row["progress_percent"] >= 100:
            month_bucket["completed_posts"] += 1
            category_bucket["completed_posts"] += 1
        month_bucket["reading_minutes"] += row["reading_minutes"] or 0
        category_bucket["reading_minutes"] += row["reading_minutes"] or 0
        month_bucket["progress_sum"] += row["progress_percent"] or 0
        category_bucket["progress_sum"] += row["progress_percent"] or 0
        if (
            month_bucket["last_read_at"] is None
            or month_at > month_bucket["last_read_at"]
        ):
            month_bucket["last_read_at"] = month_at
        if (
            category_bucket["last_read_at"] is None
            or month_at > category_bucket["last_read_at"]
        ):
            category_bucket["last_read_at"] = month_at

    for row in saved_rows:
        saved_at = row["created_at"]
        if saved_at is None:
            continue
        key = _month_key(saved_at)
        month_bucket = months[key]
        category_id = row["category_id"]
        total_posts = category_totals.get(category_id, 0)
        category_bucket = month_bucket["categories"].setdefault(
            category_id, _empty_month_category(row, total_posts)
        )
        month_bucket["saved_posts"] += 1
        category_bucket["saved_posts"] += 1

    result = []
    for (year, month), month_bucket in months.items():
        category_items = []
        month_total_posts = 0
        for category_bucket in month_bucket["categories"].values():
            total_posts = category_bucket["total_posts"]
            month_total_posts += total_posts
            category_items.append(
                {
                    "category_id": category_bucket["category_id"],
                    "category_name": category_bucket["category_name"],
                    "category_slug": category_bucket["category_slug"],
                    "total_posts": total_posts,
                    "started_posts": category_bucket["started_posts"],
                    "completed_posts": category_bucket["completed_posts"],
                    "saved_posts": category_bucket["saved_posts"],
                    "progress_percent": (
                        min(100, round(category_bucket["progress_sum"] / total_posts))
                        if total_posts
                        else 0
                    ),
                    "reading_minutes": category_bucket["reading_minutes"],
                    "last_read_at": category_bucket["last_read_at"],
                }
            )
        category_items.sort(
            key=lambda item: (-item["progress_percent"], item["category_name"])
        )
        result.append(
            {
                "year": year,
                "month": month,
                "month_label": _month_label(year, month),
                "started_posts": month_bucket["started_posts"],
                "completed_posts": month_bucket["completed_posts"],
                "saved_posts": month_bucket["saved_posts"],
                "reading_minutes": month_bucket["reading_minutes"],
                "progress_percent": (
                    min(100, round(month_bucket["progress_sum"] / month_total_posts))
                    if month_total_posts
                    else 0
                ),
                "last_read_at": month_bucket["last_read_at"],
                "categories": category_items,
            }
        )

    result.sort(key=lambda item: (item["year"], item["month"]), reverse=True)
    return result


def _writing_streak_days(rows) -> int:
    published_dates = {
        row["created_at"].date()
        for row in rows
        if row["created_at"] is not None and row["status"] == PUBLISHED_STATUS
    }
    if not published_dates:
        return 0

    streak = 0
    current = date.today()
    while current in published_dates:
        streak += 1
        current = date.fromordinal(current.toordinal() - 1)
    return streak


@router.get("/activity-summary", response_model=ActivitySummaryOut)
async def activity_summary(current_user: CurrentUser):
    user_id = current_user["id"]
    endpoint_started_at = perf_counter()
    logger.info(
        "activity_summary.called",
        extra={"endpoint": "/me/activity-summary", "user_id": user_id},
    )
    try:
        articles_read = await _timed_activity_metric(
            "articles_read",
            user_id,
            select(func.count())
            .select_from(reading_record_table)
            .where(
                (reading_record_table.c.user_id == user_id)
                & (reading_record_table.c.progress_percent >= 100)
            ),
        )
        reading_minutes = await _timed_activity_metric(
            "reading_minutes",
            user_id,
            select(func.coalesce(func.sum(reading_record_table.c.reading_minutes), 0))
            .select_from(reading_record_table)
            .where(reading_record_table.c.user_id == user_id),
        )
        post_counts_started_at = perf_counter()
        post_counts = await get_user_post_counts(user_id)
        logger.info(
            "activity_summary.post_counts_finished",
            extra={
                "endpoint": "/me/activity-summary",
                "user_id": user_id,
                "target_user_id": user_id,
                "duration_ms": round(
                    (perf_counter() - post_counts_started_at) * 1000, 2
                ),
                "published_count": post_counts["published_posts_count"],
                "draft_count": post_counts["draft_posts_count"],
                "archived_count": post_counts["archived_posts_count"],
            },
        )
        saved_posts = await _timed_activity_metric(
            "saved_posts",
            user_id,
            select(func.count())
            .select_from(saved_post_table)
            .where(saved_post_table.c.user_id == user_id),
        )

        authored_query_started_at = perf_counter()
        authored_posts = await database.fetch_all(
            select(post_table.c.created_at, post_table.c.status).where(
                post_table.c.author_id == user_id
            )
        )
        logger.info(
            "activity_summary.query_finished",
            extra={
                "endpoint": "/me/activity-summary",
                "user_id": user_id,
                "query": "authored_posts_for_writing_streak",
                "duration_ms": round(
                    (perf_counter() - authored_query_started_at) * 1000, 2
                ),
                "row_count": len(authored_posts),
            },
        )

        response = {
            "articles_read": articles_read or 0,
            "reading_minutes": reading_minutes or 0,
            "writing_streak_days": _writing_streak_days(authored_posts),
            "published_posts": post_counts["published_posts_count"],
            "draft_posts": post_counts["draft_posts_count"],
            "saved_posts": saved_posts or 0,
        }
        logger.info(
            "activity_summary.completed",
            extra={
                "endpoint": "/me/activity-summary",
                "user_id": user_id,
                "status_code": 200,
                "duration_ms": round((perf_counter() - endpoint_started_at) * 1000, 2),
                "values": response,
            },
        )
        return response
    except Exception:
        logger.exception(
            "activity_summary.failed",
            extra={
                "endpoint": "/me/activity-summary",
                "user_id": user_id,
                "status_code": 500,
                "duration_ms": round((perf_counter() - endpoint_started_at) * 1000, 2),
            },
        )
        raise


async def _settings_for_user(user_id: int) -> dict:
    row = await database.fetch_one(
        user_settings_table.select().where(user_settings_table.c.user_id == user_id)
    )
    if row is not None:
        return dict(row)
    now = datetime.now(UTC)
    return {
        "user_id": user_id,
        "notifications_enabled": True,
        "appearance": "system",
        "language": "en",
        "updated_at": now,
    }


@router.get("/settings", response_model=UserSettingsOut)
async def get_settings(current_user: CurrentUser):
    return await _settings_for_user(current_user["id"])


async def _save_settings(user_id: int, payload: UserSettingsUpdate) -> dict:
    values = payload.model_dump(exclude_unset=True)
    values["updated_at"] = datetime.now(UTC)
    existing = await database.fetch_one(
        user_settings_table.select().where(user_settings_table.c.user_id == user_id)
    )
    if existing is None:
        await database.execute(
            user_settings_table.insert().values(
                user_id=user_id,
                notifications_enabled=values.get("notifications_enabled", True),
                appearance=values.get("appearance", "system"),
                language=values.get("language", "en"),
                updated_at=values["updated_at"],
            )
        )
    else:
        await database.execute(
            user_settings_table.update()
            .where(user_settings_table.c.user_id == user_id)
            .values(**values)
        )
    return await _settings_for_user(user_id)


@router.post("/settings", response_model=UserSettingsOut)
async def save_settings(payload: UserSettingsUpdate, current_user: CurrentUser):
    return await _save_settings(current_user["id"], payload)


@router.put("/settings", response_model=UserSettingsOut)
async def update_settings(payload: UserSettingsUpdate, current_user: CurrentUser):
    return await _save_settings(current_user["id"], payload)


@router.put("/device-token", response_model=DeviceTokenOut)
async def upsert_device_token(payload: DeviceTokenIn, current_user: CurrentUser):
    now = datetime.now(UTC)
    existing = await database.fetch_one(
        user_device_token_table.select().where(
            user_device_token_table.c.fcm_token == payload.fcm_token
        )
    )
    values = {
        "user_id": current_user["id"],
        "platform": payload.platform,
        "device_name": payload.device_name,
        "is_active": True,
        "updated_at": now,
    }

    if existing is None:
        token_id = await database.execute(
            user_device_token_table.insert().values(
                fcm_token=payload.fcm_token,
                created_at=now,
                **values,
            )
        )
    else:
        token_id = existing["id"]
        await database.execute(
            user_device_token_table.update()
            .where(user_device_token_table.c.id == token_id)
            .values(**values)
        )

    row = await database.fetch_one(
        user_device_token_table.select().where(user_device_token_table.c.id == token_id)
    )
    return dict(row)
