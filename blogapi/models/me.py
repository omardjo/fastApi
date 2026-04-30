from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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


class ReadingJourneyCategoryOut(BaseModel):
    category_id: int
    category_name: str
    category_slug: str
    total_posts: int
    started_posts: int
    completed_posts: int
    saved_posts: int
    progress_percent: int
    reading_minutes: int
    last_read_at: datetime | None = None


class ReadingJourneyMonthOut(BaseModel):
    year: int
    month: int
    month_label: str
    started_posts: int
    completed_posts: int
    saved_posts: int
    reading_minutes: int
    progress_percent: int
    last_read_at: datetime | None = None
    categories: list[ReadingJourneyCategoryOut] = Field(default_factory=list)


class ReadingJourneyOut(BaseModel):
    categories: list[ReadingJourneyCategoryOut] = Field(default_factory=list)
    months: list[ReadingJourneyMonthOut] = Field(default_factory=list)


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
    language: Literal["fr", "en"] = "en"
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class UserSettingsUpdate(BaseModel):
    notifications_enabled: bool | None = None
    appearance: Literal["system", "light", "dark"] | None = None
    language: Literal["fr", "en"] | None = None


class ImageUploadOut(BaseModel):
    url: str
    filename: str
    content_type: str
    size: int
