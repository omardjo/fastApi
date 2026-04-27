from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from blogapi.database import (
    database,
    post_table,
    reading_record_table,
    saved_post_table,
    user_settings_table,
)
from blogapi.models.me import (
    ActivitySummaryOut,
    ReadingRecordIn,
    ReadingRecordOut,
    SavedPostOut,
    UserSettingsOut,
    UserSettingsUpdate,
)
from blogapi.routers.post import find_post, _post_summary, _reading_minutes
from blogapi.security import get_current_user

router = APIRouter(prefix="/me", tags=["me"])
CurrentUser = Annotated[dict, Depends(get_current_user)]


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


def _writing_streak_days(rows) -> int:
    published_dates = {
        row["created_at"].date()
        for row in rows
        if row["created_at"] is not None and row["status"] == "published"
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
    articles_read = await database.fetch_val(
        select(func.count())
        .select_from(reading_record_table)
        .where(
            (reading_record_table.c.user_id == user_id)
            & (reading_record_table.c.progress_percent >= 100)
        )
    )
    reading_minutes = await database.fetch_val(
        select(func.coalesce(func.sum(reading_record_table.c.reading_minutes), 0))
        .select_from(reading_record_table)
        .where(reading_record_table.c.user_id == user_id)
    )
    published_posts = await database.fetch_val(
        select(func.count())
        .select_from(post_table)
        .where(
            (post_table.c.author_id == user_id) & (post_table.c.status == "published")
        )
    )
    draft_posts = await database.fetch_val(
        select(func.count())
        .select_from(post_table)
        .where((post_table.c.author_id == user_id) & (post_table.c.status == "draft"))
    )
    saved_posts = await database.fetch_val(
        select(func.count())
        .select_from(saved_post_table)
        .where(saved_post_table.c.user_id == user_id)
    )
    authored_posts = await database.fetch_all(
        post_table.select().where(post_table.c.author_id == user_id)
    )
    return {
        "articles_read": articles_read or 0,
        "reading_minutes": reading_minutes or 0,
        "writing_streak_days": _writing_streak_days(authored_posts),
        "published_posts": published_posts or 0,
        "draft_posts": draft_posts or 0,
        "saved_posts": saved_posts or 0,
    }


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


@router.put("/settings", response_model=UserSettingsOut)
async def update_settings(payload: UserSettingsUpdate, current_user: CurrentUser):
    values = payload.model_dump(exclude_unset=True)
    values["updated_at"] = datetime.now(UTC)
    existing = await database.fetch_one(
        user_settings_table.select().where(
            user_settings_table.c.user_id == current_user["id"]
        )
    )
    if existing is None:
        await database.execute(
            user_settings_table.insert().values(
                user_id=current_user["id"],
                notifications_enabled=values.get("notifications_enabled", True),
                appearance=values.get("appearance", "system"),
                language=values.get("language", "en"),
                updated_at=values["updated_at"],
            )
        )
    else:
        await database.execute(
            user_settings_table.update()
            .where(user_settings_table.c.user_id == current_user["id"])
            .values(**values)
        )
    return await _settings_for_user(current_user["id"])
