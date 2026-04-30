from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints


class UserPreviewOut(BaseModel):
    id: int
    username: str
    display_name: str | None = None
    bio: str | None = None
    avatar_url: str | None = None

    model_config = ConfigDict(from_attributes=True)


class UserListOut(BaseModel):
    items: list[UserPreviewOut]
    page: int
    limit: int
    total: int


class UserPublicProfileOut(UserPreviewOut):
    followers_count: int = 0
    following_count: int = 0
    is_following: bool = False


class FollowOut(BaseModel):
    follower_id: int
    following_id: int
    created_at: datetime
    follower: UserPreviewOut | None = None
    following: UserPreviewOut | None = None


class FollowStatusOut(BaseModel):
    user_id: int
    is_following: bool


class DeviceTokenIn(BaseModel):
    fcm_token: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4096)
    ]
    platform: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)
    ] = "android"
    device_name: Annotated[
        str | None, StringConstraints(strip_whitespace=True, max_length=255)
    ] = None


class DeviceTokenOut(BaseModel):
    id: int
    user_id: int
    fcm_token: str
    platform: str
    device_name: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationTestIn(BaseModel):
    token: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4096)
    ]
    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
    ]
    body: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
    ]
    data: dict[str, str] | None = None


class NotificationSendOut(BaseModel):
    sent: bool
    message_id: str | None = None
    reason: str | None = None
    firebase_configured: bool = False
