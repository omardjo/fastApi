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
    email: EmailStr
    password: PasswordStr


class UserLogin(UserCreate):
    pass


class User(BaseModel):
    id: int
    email: EmailStr

    model_config = ConfigDict(from_attributes=True)


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
