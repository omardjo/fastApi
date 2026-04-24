from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints


BodyStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2000),
]


class UserPostIn(BaseModel):
    body: BodyStr


class UserPost(UserPostIn):
    id: int

    model_config = ConfigDict(from_attributes=True)


class CommentIn(BaseModel):
    body: BodyStr
    post_id: int


class Comment(
    CommentIn
):  # comment Out is the name of the class, and it inherits from CommentIn, which means it will have all the fields of CommentIn, plus any additional fields we define in Comment to fasten the development process.
    id: int

    model_config = ConfigDict(from_attributes=True)


class UserPostWithComments(BaseModel):
    post: UserPost
    comments: list[Comment]


# response example for UserPostWithComments
# response = {"post": {"id": 0, "body": "My post"},
# "comments": [{"id": 2, "body": "This is a comment", "post_id": 0}],
# }
