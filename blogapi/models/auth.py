from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

EmailStr = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=5,
        max_length=255,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    ),
]
PasswordStr = Annotated[
    str,
    StringConstraints(min_length=8, max_length=128),
]


class UserCreate(BaseModel):
    username: Annotated[
        str | None,
        StringConstraints(
            strip_whitespace=True,
            min_length=3,
            max_length=150,
            pattern=r"^[A-Za-z0-9_]+$",
        ),
    ] = None
    email: EmailStr
    password: PasswordStr


class UserLogin(UserCreate):
    pass


class User(BaseModel):
    id: int
    username: str
    email: EmailStr
    display_name: str | None = None
    bio: str | None = None
    avatar_url: str | None = None
    role: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CurrentUserProfile(BaseModel):
    id: int
    email: EmailStr
    username: str
    display_name: str | None = None
    bio: str | None = None
    avatar_url: str | None = None
    created_at: datetime
    posts_count: int = 0
    comments_count: int = 0
    saved_posts_count: int = 0
    followers_count: int = 0
    following_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class CurrentUserUpdate(BaseModel):
    username: Annotated[
        str | None,
        StringConstraints(
            strip_whitespace=True,
            min_length=3,
            max_length=150,
            pattern=r"^[A-Za-z0-9_]+$",
        ),
    ] = None
    display_name: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=150),
    ] = None
    bio: Annotated[
        str | None, StringConstraints(strip_whitespace=True, max_length=2000)
    ] = None
    avatar_url: Annotated[
        str | None, StringConstraints(strip_whitespace=True, max_length=1024)
    ] = None


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: User


class RefreshTokenRequest(BaseModel):
    refresh_token: Annotated[str, StringConstraints(min_length=32, max_length=512)]


class LogoutRequest(BaseModel):
    refresh_token: Annotated[str, StringConstraints(min_length=32, max_length=512)]
