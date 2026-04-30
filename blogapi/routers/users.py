from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select

from blogapi.database import database, user_follow_table, user_table
from blogapi.models.users import (
    FollowOut,
    FollowStatusOut,
    UserListOut,
    UserPreviewOut,
    UserPublicProfileOut,
)
from blogapi.security import get_current_user

router = APIRouter(prefix="/users", tags=["users"])
CurrentUser = Annotated[dict, Depends(get_current_user)]


async def _user_or_404(user_id: int):
    user = await database.fetch_one(
        user_table.select().where(user_table.c.id == user_id)
    )
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _user_preview(row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "bio": row["bio"],
        "avatar_url": row["avatar_url"],
    }


def _visible_users_filter():
    return user_table.c.role != "system"


async def _is_following(follower_id: int, following_id: int) -> bool:
    row = await database.fetch_one(
        user_follow_table.select().where(
            (user_follow_table.c.follower_id == follower_id)
            & (user_follow_table.c.following_id == following_id)
        )
    )
    return row is not None


async def _user_public_profile(user_row, current_user_id: int) -> dict:
    user_id = user_row["id"]
    followers_count = await database.fetch_val(
        select(func.count())
        .select_from(user_follow_table)
        .where(user_follow_table.c.following_id == user_id)
    )
    following_count = await database.fetch_val(
        select(func.count())
        .select_from(user_follow_table)
        .where(user_follow_table.c.follower_id == user_id)
    )
    return {
        **_user_preview(user_row),
        "followers_count": followers_count or 0,
        "following_count": following_count or 0,
        "is_following": await _is_following(current_user_id, user_id),
    }


async def _follow_out(follower_id: int, following_id: int) -> dict:
    follow = await database.fetch_one(
        user_follow_table.select().where(
            (user_follow_table.c.follower_id == follower_id)
            & (user_follow_table.c.following_id == following_id)
        )
    )
    if follow is None:
        raise HTTPException(status_code=404, detail="Follow relationship not found")

    follower = await _user_or_404(follower_id)
    following = await _user_or_404(following_id)
    return {
        "follower_id": follower_id,
        "following_id": following_id,
        "created_at": follow["created_at"],
        "follower": _user_preview(follower),
        "following": _user_preview(following),
    }


@router.get("", response_model=UserListOut)
async def list_users(
    current_user: CurrentUser,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=50),
    search: str | None = Query(default=None, min_length=1, max_length=150),
):
    filters = [_visible_users_filter()]
    if search:
        pattern = f"%{search.strip().lower()}%"
        filters.append(
            (func.lower(user_table.c.username).like(pattern))
            | (func.lower(user_table.c.display_name).like(pattern))
            | (func.lower(user_table.c.email).like(pattern))
        )

    where_clause = filters[0]
    for item in filters[1:]:
        where_clause = where_clause & item

    total = await database.fetch_val(
        select(func.count()).select_from(user_table).where(where_clause)
    )
    rows = await database.fetch_all(
        user_table.select()
        .where(where_clause)
        .order_by(func.lower(user_table.c.username).asc())
        .limit(limit)
        .offset((page - 1) * limit)
    )
    return {
        "items": [_user_preview(row) for row in rows],
        "page": page,
        "limit": limit,
        "total": total or 0,
    }


@router.get("/{user_id}", response_model=UserPublicProfileOut)
async def get_user(user_id: int, current_user: CurrentUser):
    user = await _user_or_404(user_id)
    if user["role"] == "system":
        raise HTTPException(status_code=404, detail="User not found")
    return await _user_public_profile(user, current_user["id"])


@router.post(
    "/{user_id}/follow",
    response_model=FollowOut,
    status_code=status.HTTP_201_CREATED,
)
async def follow_user(user_id: int, current_user: CurrentUser):
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Users cannot follow themselves")

    await _user_or_404(user_id)
    existing = await database.fetch_one(
        user_follow_table.select().where(
            (user_follow_table.c.follower_id == current_user["id"])
            & (user_follow_table.c.following_id == user_id)
        )
    )
    if existing is None:
        await database.execute(
            user_follow_table.insert().values(
                follower_id=current_user["id"],
                following_id=user_id,
                created_at=datetime.now(UTC),
            )
        )

    return await _follow_out(current_user["id"], user_id)


@router.delete("/{user_id}/follow", status_code=status.HTTP_204_NO_CONTENT)
async def unfollow_user(user_id: int, current_user: CurrentUser):
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Users cannot unfollow themselves")

    await _user_or_404(user_id)
    existing = await database.fetch_one(
        user_follow_table.select().where(
            (user_follow_table.c.follower_id == current_user["id"])
            & (user_follow_table.c.following_id == user_id)
        )
    )
    if existing is None:
        raise HTTPException(status_code=404, detail="Follow relationship not found")

    await database.execute(
        user_follow_table.delete().where(
            (user_follow_table.c.follower_id == current_user["id"])
            & (user_follow_table.c.following_id == user_id)
        )
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{user_id}/followers", response_model=list[UserPreviewOut])
async def list_followers(user_id: int, current_user: CurrentUser):
    await _user_or_404(user_id)
    query = (
        select(user_table)
        .select_from(
            user_follow_table.join(
                user_table, user_follow_table.c.follower_id == user_table.c.id
            )
        )
        .where(user_follow_table.c.following_id == user_id)
        .order_by(func.lower(user_table.c.username).asc())
    )
    rows = await database.fetch_all(query)
    return [_user_preview(row) for row in rows]


@router.get("/{user_id}/following", response_model=list[UserPreviewOut])
async def list_following(user_id: int, current_user: CurrentUser):
    await _user_or_404(user_id)
    query = (
        select(user_table)
        .select_from(
            user_follow_table.join(
                user_table, user_follow_table.c.following_id == user_table.c.id
            )
        )
        .where(user_follow_table.c.follower_id == user_id)
        .order_by(func.lower(user_table.c.username).asc())
    )
    rows = await database.fetch_all(query)
    return [_user_preview(row) for row in rows]


@router.get("/{user_id}/follow-status", response_model=FollowStatusOut)
async def follow_status(user_id: int, current_user: CurrentUser):
    await _user_or_404(user_id)
    row = await database.fetch_one(
        user_follow_table.select().where(
            (user_follow_table.c.follower_id == current_user["id"])
            & (user_follow_table.c.following_id == user_id)
        )
    )
    return {"user_id": user_id, "is_following": row is not None}
