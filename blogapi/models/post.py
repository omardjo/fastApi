from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

BodyStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2000),
]
ContentStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=50000),
]
TitleStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
]
SlugStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
]
NameStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
]
TagNameStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=80),
]
PostStatus = Literal["draft", "published", "archived"]


class UserPostIn(BaseModel):
    body: BodyStr


class UserPost(UserPostIn):
    id: int

    model_config = ConfigDict(from_attributes=True)


class CommentIn(BaseModel):
    body: BodyStr
    post_id: int


class CommentAuthorOut(BaseModel):
    id: int
    username: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None

    model_config = ConfigDict(from_attributes=True)


class Comment(
    CommentIn
):  # comment Out is the name of the class, and it inherits from CommentIn, which means it will have all the fields of CommentIn, plus any additional fields we define in Comment to fasten the development process.
    id: int
    created_at: datetime
    author_id: int
    author: "CommentAuthorOut | None" = None

    model_config = ConfigDict(from_attributes=True)


class UserPostWithComments(BaseModel):
    post: UserPost
    comments: list[Comment]


class CategoryCreate(BaseModel):
    name: NameStr
    slug: SlugStr


class CategoryOut(CategoryCreate):
    id: int
    posts_count: int | None = None

    model_config = ConfigDict(from_attributes=True)


class TagCreate(BaseModel):
    name: TagNameStr


class TagOut(TagCreate):
    id: int
    posts_count: int | None = None

    model_config = ConfigDict(from_attributes=True)


class PostCreate(BaseModel):
    title: TitleStr
    content: ContentStr
    category_id: int
    tags: list[TagNameStr] = Field(default_factory=list)
    status: PostStatus = "draft"
    slug: SlugStr | None = None
    cover_image_url: Annotated[
        str | None, StringConstraints(strip_whitespace=True, max_length=1024)
    ] = None
    thumbnail_url: Annotated[
        str | None, StringConstraints(strip_whitespace=True, max_length=1024)
    ] = None
    excerpt: Annotated[
        str | None, StringConstraints(strip_whitespace=True, max_length=1000)
    ] = None
    summary: Annotated[
        str | None, StringConstraints(strip_whitespace=True, max_length=1000)
    ] = None


class PostUpdate(BaseModel):
    title: TitleStr | None = None
    content: ContentStr | None = None
    category_id: int | None = None
    tags: list[TagNameStr] | None = None
    status: PostStatus | None = None
    slug: SlugStr | None = None
    cover_image_url: Annotated[
        str | None, StringConstraints(strip_whitespace=True, max_length=1024)
    ] = None
    thumbnail_url: Annotated[
        str | None, StringConstraints(strip_whitespace=True, max_length=1024)
    ] = None
    excerpt: Annotated[
        str | None, StringConstraints(strip_whitespace=True, max_length=1000)
    ] = None
    summary: Annotated[
        str | None, StringConstraints(strip_whitespace=True, max_length=1000)
    ] = None


class PostAuthorOut(BaseModel):
    id: int
    username: str | None = None
    email: str
    display_name: str | None = None
    avatar_url: str | None = None

    model_config = ConfigDict(from_attributes=True)


class PostSummaryOut(BaseModel):
    id: int
    title: str
    slug: str
    status: str
    created_at: datetime
    updated_at: datetime
    cover_image_url: str | None = None
    thumbnail_url: str | None = None
    excerpt: str | None = None
    summary: str | None = None
    reading_minutes: int
    author: PostAuthorOut
    category: CategoryOut
    tags: list[TagOut] = Field(default_factory=list)


class PostCommentCreate(BaseModel):
    body: BodyStr


class PostCommentOut(BaseModel):
    id: int
    body: str
    created_at: datetime
    post_id: int
    author_id: int
    author: "CommentAuthorOut | None" = None

    model_config = ConfigDict(from_attributes=True)


class PostDetailOut(PostSummaryOut):
    content: str
    comments: list[PostCommentOut] = Field(default_factory=list)


# response example for UserPostWithComments
# response = {"post": {"id": 0, "body": "My post"},
# "comments": [{"id": 2, "body": "This is a comment", "post_id": 0}],
# }
