from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from blogapi.models.post import PostSummaryOut


class SavedPostOut(BaseModel):
    post: PostSummaryOut
    saved_at: datetime


class ReadingRecordIn(BaseModel):
    progress_percent: int = Field(ge=0, le=100)
    reading_minutes: int | None = Field(default=None, ge=0)


class ReadingRecordOut(BaseModel):
    post_id: int
    progress_percent: int
    reading_minutes: int
    completed_at: datetime | None = None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ActivitySummaryOut(BaseModel):
    articles_read: int
    reading_minutes: int
    writing_streak_days: int
    published_posts: int
    draft_posts: int
    saved_posts: int


class UserSettingsOut(BaseModel):
    notifications_enabled: bool = True
    appearance: Literal["system", "light", "dark"] = "system"
    language: str = "en"
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class UserSettingsUpdate(BaseModel):
    notifications_enabled: bool | None = None
    appearance: Literal["system", "light", "dark"] | None = None
    language: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, min_length=2, max_length=16),
    ] = None


class ImageUploadOut(BaseModel):
    url: str
    filename: str
    content_type: str
    size: int
