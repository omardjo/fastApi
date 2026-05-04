from sqlalchemy import func, select

from blogapi.database import database, post_table
from blogapi.models.post import ARCHIVED_STATUS, DRAFT_STATUS, PUBLISHED_STATUS

POST_COUNT_STATUSES = (DRAFT_STATUS, PUBLISHED_STATUS, ARCHIVED_STATUS)


async def get_user_post_counts(user_id: int) -> dict[str, int]:
    rows = await database.fetch_all(
        select(
            func.lower(post_table.c.status).label("status"), func.count().label("count")
        )
        .select_from(post_table)
        .where(post_table.c.author_id == user_id)
        .group_by(func.lower(post_table.c.status))
    )
    by_status = {status: 0 for status in POST_COUNT_STATUSES}
    other_posts_count = 0
    for row in rows:
        status = row["status"]
        count = row["count"] or 0
        if status in by_status:
            by_status[status] = count
        else:
            other_posts_count += count

    total_posts_count = sum(by_status.values()) + other_posts_count
    return {
        "posts_count": total_posts_count,
        "published_posts_count": by_status[PUBLISHED_STATUS],
        "draft_posts_count": by_status[DRAFT_STATUS],
        "archived_posts_count": by_status[ARCHIVED_STATUS],
    }
