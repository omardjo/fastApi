from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError

from blogapi.database import (
    category_table,
    comment_table,
    database,
    post_table,
    post_tag_table,
    reading_record_table,
    tag_table,
    user_table,
)
from blogapi.models.me import ReadingRecordIn, ReadingRecordOut
from blogapi.models.post import (
    CategoryCreate,
    CategoryOut,
    Comment,
    CommentIn,
    PostCommentCreate,
    PostCommentOut,
    PostCreate,
    PostDetailOut,
    PostSummaryOut,
    PostUpdate,
    TagCreate,
    TagOut,
    UserPost,
    UserPostIn,
    UserPostWithComments,
)
from blogapi.security import get_current_user
from blogapi.services.firebase_notifications import notify_followers_about_new_post

router = APIRouter(dependencies=[Depends(get_current_user)])


async def find_post(post_id: int):
    query = post_table.select().where(post_table.c.id == post_id)
    return await database.fetch_one(query)


def _slugify(value: str) -> str:
    clean = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
    while "--" in clean:
        clean = clean.replace("--", "-")
    return clean.strip("-") or "post"


def _reading_minutes(content: str) -> int:
    words = len((content or "").split())
    return max(1, (words + 199) // 200)


def _excerpt(content: str, explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    clean = " ".join((content or "").split())
    if not clean:
        return None
    return clean[:240]


async def _category_by_id(category_id: int):
    return await database.fetch_one(
        category_table.select().where(category_table.c.id == category_id)
    )


async def _default_category_id() -> int:
    category = await database.fetch_one(
        category_table.select().where(category_table.c.slug == "uncategorized")
    )
    if category is not None:
        return category["id"]

    try:
        return await database.execute(
            category_table.insert().values(name="Uncategorized", slug="uncategorized")
        )
    except IntegrityError:
        category = await database.fetch_one(
            category_table.select().where(category_table.c.slug == "uncategorized")
        )
        return category["id"]


async def _unique_post_slug(base_slug: str) -> str:
    slug = base_slug
    suffix = 2
    while await database.fetch_one(
        post_table.select().where(post_table.c.slug == slug)
    ):
        slug = f"{base_slug}-{suffix}"
        suffix += 1
    return slug


async def _ensure_tags(tag_names: list[str]) -> list[int]:
    tag_ids: list[int] = []
    for raw_name in tag_names:
        name = raw_name.strip()
        if not name:
            continue
        existing = await database.fetch_one(
            tag_table.select().where(func.lower(tag_table.c.name) == name.lower())
        )
        if existing is not None:
            tag_ids.append(existing["id"])
            continue
        try:
            tag_id = await database.execute(tag_table.insert().values(name=name))
            tag_ids.append(tag_id)
        except IntegrityError:
            existing = await database.fetch_one(
                tag_table.select().where(func.lower(tag_table.c.name) == name.lower())
            )
            if existing is not None:
                tag_ids.append(existing["id"])
    return list(dict.fromkeys(tag_ids))


async def _replace_post_tags(post_id: int, tag_ids: list[int]) -> None:
    await database.execute(
        post_tag_table.delete().where(post_tag_table.c.post_id == post_id)
    )
    for tag_id in tag_ids:
        await database.execute(
            post_tag_table.insert().values(post_id=post_id, tag_id=tag_id)
        )


async def _post_tags(post_id: int) -> list[dict]:
    query = (
        select(tag_table.c.id, tag_table.c.name)
        .select_from(
            post_tag_table.join(tag_table, post_tag_table.c.tag_id == tag_table.c.id)
        )
        .where(post_tag_table.c.post_id == post_id)
        .order_by(tag_table.c.name.asc())
    )
    rows = await database.fetch_all(query)
    return [dict(row) for row in rows]


async def _post_summary(post_row) -> dict:
    post_data = dict(post_row)
    category = None
    author = None
    if post_data.get("category_id") is not None:
        category = await _category_by_id(post_data["category_id"])
    if post_data.get("author_id") is not None:
        author = await database.fetch_one(
            user_table.select().where(user_table.c.id == post_data["author_id"])
        )
    content = post_data.get("content") or post_data.get("body") or ""
    return {
        "id": post_data["id"],
        "title": post_data.get("title") or post_data.get("body") or "",
        "slug": post_data.get("slug") or _slugify(post_data.get("title") or "post"),
        "status": post_data.get("status") or "draft",
        "created_at": post_data.get("created_at") or datetime.now(UTC),
        "updated_at": post_data.get("updated_at")
        or post_data.get("created_at")
        or datetime.now(UTC),
        "cover_image_url": post_data.get("cover_image_url"),
        "thumbnail_url": post_data.get("thumbnail_url"),
        "excerpt": _excerpt(content, post_data.get("excerpt")),
        "summary": _excerpt(content, post_data.get("excerpt")),
        "reading_minutes": _reading_minutes(content),
        "author": dict(author) if author is not None else None,
        "category": dict(category) if category is not None else None,
        "tags": await _post_tags(post_data["id"]),
    }


async def _comment_out(comment_row) -> dict:
    comment = dict(comment_row)
    author = await database.fetch_one(
        user_table.select().where(user_table.c.id == comment["author_id"])
    )
    return {
        **comment,
        "author": (
            {
                "id": author["id"],
                "username": author["username"],
                "display_name": author["display_name"],
                "avatar_url": author["avatar_url"],
            }
            if author is not None
            else None
        ),
    }


async def _post_detail(post_row) -> dict:
    post_data = dict(post_row)
    summary = await _post_summary(post_row)
    comments = await database.fetch_all(
        comment_table.select()
        .where(comment_table.c.post_id == post_data["id"])
        .order_by(comment_table.c.created_at.asc())
    )
    return {
        **summary,
        "content": post_data.get("content") or post_data.get("body") or "",
        "comments": [await _comment_out(comment) for comment in comments],
    }


@router.post("/post", response_model=UserPost | PostDetailOut, status_code=201)
async def create_post(
    post: UserPostIn | PostCreate, current_user=Depends(get_current_user)
):
    if isinstance(post, PostCreate):
        return await create_post_v2(post, current_user)

    slug = await _unique_post_slug(_slugify(post.body[:80]))
    data = {
        "body": post.body,
        "title": post.body[:255],
        "content": post.body,
        "slug": slug,
        "status": "draft",
        "author_id": current_user["id"],
        "category_id": await _default_category_id(),
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    query = post_table.insert().values(data)
    last_record_id = await database.execute(query)
    return {"id": last_record_id, "body": post.body}


@router.get("/post", response_model=list[UserPost])
async def get_all_posts():
    query = post_table.select()
    rows = await database.fetch_all(query)
    return [{"id": row["id"], "body": row["body"]} for row in rows]


@router.post("/comment", response_model=Comment, status_code=201)
async def create_comment(comment: CommentIn, current_user=Depends(get_current_user)):
    post = await find_post(comment.post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    data = comment.model_dump()
    data["author_id"] = current_user["id"]
    data["created_at"] = datetime.now(UTC)
    query = comment_table.insert().values(data)
    last_record_id = await database.execute(query)
    return {
        "body": data["body"],
        "post_id": data["post_id"],
        "created_at": data["created_at"],
        "author_id": data["author_id"],
        "id": last_record_id,
        "author": {
            "id": current_user["id"],
            "username": current_user["username"],
            "display_name": current_user["display_name"],
            "avatar_url": current_user["avatar_url"],
        },
    }  # ** used to unpack the data dictionary and add the id to it because it uses key pair values and we want to add the id key with the value of last_record_id to the data dictionary and return it as a response


@router.get("/post/{post_id}/comment", response_model=list[Comment])
async def get_comments_on_post(post_id: int):
    query = comment_table.select().where(comment_table.c.post_id == post_id)
    rows = await database.fetch_all(query)
    return [await _comment_out(row) for row in rows]


@router.get("/post/{post_id}", response_model=UserPostWithComments)
async def get_post_with_comments(post_id: int):
    post = await find_post(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    return {
        "post": {"id": post["id"], "body": post["body"]},
        "comments": await get_comments_on_post(post_id),
    }


@router.post(
    "/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED
)
async def create_category(payload: CategoryCreate):
    try:
        category_id = await database.execute(
            category_table.insert().values(name=payload.name, slug=payload.slug)
        )
    except IntegrityError:
        raise HTTPException(status_code=400, detail="Duplicate category name or slug")
    category = await database.fetch_one(
        category_table.select().where(category_table.c.id == category_id)
    )
    return dict(category)


@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(
    include_counts: bool = Query(default=False),
    status_value: str | None = Query(default="published", alias="status"),
):
    categories = await database.fetch_all(
        category_table.select().order_by(category_table.c.name.asc())
    )
    result = []
    for category in categories:
        item = dict(category)
        if include_counts:
            count_query = (
                select(func.count())
                .select_from(post_table)
                .where(post_table.c.category_id == category["id"])
            )
            if status_value:
                count_query = count_query.where(
                    func.lower(post_table.c.status) == status_value.lower()
                )
            item["posts_count"] = await database.fetch_val(count_query) or 0
        result.append(item)
    return result


@router.post("/tags", response_model=TagOut, status_code=status.HTTP_201_CREATED)
async def create_tag(payload: TagCreate):
    try:
        tag_id = await database.execute(tag_table.insert().values(name=payload.name))
    except IntegrityError:
        raise HTTPException(status_code=400, detail="Duplicate tag name")
    tag = await database.fetch_one(tag_table.select().where(tag_table.c.id == tag_id))
    return dict(tag)


@router.get("/tags", response_model=list[TagOut])
async def list_tags(
    include_counts: bool = Query(default=False),
    status_value: str | None = Query(default="published", alias="status"),
):
    tags = await database.fetch_all(tag_table.select().order_by(tag_table.c.name.asc()))
    result = []
    for tag_row in tags:
        item = dict(tag_row)
        if include_counts:
            count_query = (
                select(func.count())
                .select_from(
                    post_tag_table.join(
                        post_table, post_tag_table.c.post_id == post_table.c.id
                    )
                )
                .where(post_tag_table.c.tag_id == tag_row["id"])
            )
            if status_value:
                count_query = count_query.where(
                    func.lower(post_table.c.status) == status_value.lower()
                )
            item["posts_count"] = await database.fetch_val(count_query) or 0
        result.append(item)
    return result


@router.post(
    "/posts", response_model=PostDetailOut, status_code=status.HTTP_201_CREATED
)
async def create_post_v2(payload: PostCreate, current_user=Depends(get_current_user)):
    category = await _category_by_id(payload.category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")

    slug = payload.slug or await _unique_post_slug(_slugify(payload.title))
    data = {
        "title": payload.title,
        "slug": slug,
        "content": payload.content,
        "body": payload.content,
        "status": payload.status,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "author_id": current_user["id"],
        "category_id": payload.category_id,
        "cover_image_url": payload.cover_image_url,
        "thumbnail_url": payload.thumbnail_url,
        "excerpt": payload.excerpt or payload.summary,
    }
    try:
        post_id = await database.execute(post_table.insert().values(data))
    except IntegrityError:
        raise HTTPException(status_code=400, detail="Duplicate post slug")

    tag_ids = await _ensure_tags(payload.tags)
    await _replace_post_tags(post_id, tag_ids)

    created = await find_post(post_id)
    if payload.status == "published":
        await notify_followers_about_new_post(
            author_id=current_user["id"], post_id=post_id, post_title=payload.title
        )
    return await _post_detail(created)


@router.get("/posts", response_model=list[PostSummaryOut])
async def list_posts(
    category_slug: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    author_id: int | None = Query(default=None),
    author: str | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
):
    query = select(post_table)
    if category_slug:
        query = query.join(
            category_table, post_table.c.category_id == category_table.c.id
        ).where(func.lower(category_table.c.slug) == category_slug.lower())
    if tag:
        query = (
            query.join(post_tag_table, post_table.c.id == post_tag_table.c.post_id)
            .join(tag_table, post_tag_table.c.tag_id == tag_table.c.id)
            .where(func.lower(tag_table.c.name) == tag.lower())
        )
    filters = []
    if author_id is not None:
        filters.append(post_table.c.author_id == author_id)
    if author is not None:
        author_row = await database.fetch_one(
            user_table.select().where(
                (func.lower(user_table.c.username) == author.lower())
                | (func.lower(user_table.c.email) == author.lower())
            )
        )
        if author_row is None:
            return []
        filters.append(post_table.c.author_id == author_row["id"])
    if status_value is not None:
        filters.append(func.lower(post_table.c.status) == status_value.lower())
    if filters:
        query = query.where(and_(*filters))

    query = query.order_by(post_table.c.created_at.desc())
    rows = await database.fetch_all(query)
    summaries = []
    seen: set[int] = set()
    for row in rows:
        post_id = row["id"]
        if post_id in seen:
            continue
        seen.add(post_id)
        summaries.append(await _post_summary(row))
    return summaries


@router.get("/posts/{post_id}", response_model=PostDetailOut)
async def get_post(post_id: int):
    post = await find_post(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    return await _post_detail(post)


@router.post("/posts/{post_id}/reading-progress", response_model=ReadingRecordOut)
async def upsert_post_reading_progress(
    post_id: int, payload: ReadingRecordIn, current_user=Depends(get_current_user)
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


@router.put("/posts/{post_id}", response_model=PostDetailOut)
async def update_post(
    post_id: int, payload: PostUpdate, current_user=Depends(get_current_user)
):
    post = await find_post(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    if post["author_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not allowed to modify this post")

    values = payload.model_dump(exclude_none=True)
    tags = values.pop("tags", None)
    summary = values.pop("summary", None)
    if "category_id" in values:
        category = await _category_by_id(values["category_id"])
        if category is None:
            raise HTTPException(status_code=404, detail="Category not found")
    if "content" in values:
        values["body"] = values["content"]
    if summary is not None and "excerpt" not in values:
        values["excerpt"] = summary
    if "title" in values and "slug" not in values:
        values["slug"] = _slugify(values["title"])
    values["updated_at"] = datetime.now(UTC)

    if values:
        try:
            await database.execute(
                post_table.update().where(post_table.c.id == post_id).values(**values)
            )
        except IntegrityError:
            raise HTTPException(status_code=400, detail="Duplicate post slug")

    if tags is not None:
        tag_ids = await _ensure_tags(tags)
        await _replace_post_tags(post_id, tag_ids)

    updated = await find_post(post_id)
    if (
        payload.status == "published"
        and post["status"] != "published"
        and updated is not None
    ):
        await notify_followers_about_new_post(
            author_id=current_user["id"],
            post_id=post_id,
            post_title=updated["title"],
        )
    return await _post_detail(updated)


@router.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(post_id: int, current_user=Depends(get_current_user)):
    post = await find_post(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    if post["author_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not allowed to modify this post")
    await database.execute(post_table.delete().where(post_table.c.id == post_id))


@router.post(
    "/posts/{post_id}/comments",
    response_model=PostCommentOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_post_comment(
    post_id: int,
    payload: PostCommentCreate,
    current_user=Depends(get_current_user),
):
    post = await find_post(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")

    created_at = datetime.now(UTC)
    comment_id = await database.execute(
        comment_table.insert().values(
            body=payload.body,
            post_id=post_id,
            author_id=current_user["id"],
            created_at=created_at,
        )
    )
    return {
        "id": comment_id,
        "body": payload.body,
        "created_at": created_at,
        "post_id": post_id,
        "author_id": current_user["id"],
        "author": {
            "id": current_user["id"],
            "username": current_user["username"],
            "display_name": current_user["display_name"],
            "avatar_url": current_user["avatar_url"],
        },
    }


@router.get("/posts/{post_id}/comments", response_model=list[PostCommentOut])
async def list_post_comments(post_id: int):
    post = await find_post(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")

    rows = await database.fetch_all(
        comment_table.select()
        .where(comment_table.c.post_id == post_id)
        .order_by(comment_table.c.created_at.asc())
    )
    return [await _comment_out(row) for row in rows]


# await simply make sure that this function get called and finished running before continuing the execution of this line of code here
# Asyyn function can sometimes be run in parallel
