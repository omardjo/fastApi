from typing import Annotated

from fastapi import APIRouter, Depends

from blogapi.models.users import NotificationSendOut, NotificationTestIn
from blogapi.security import get_current_user
from blogapi.services.firebase_notifications import send_push_notification

router = APIRouter(prefix="/notifications", tags=["notifications"])
CurrentUser = Annotated[dict, Depends(get_current_user)]


@router.post("/test", response_model=NotificationSendOut)
async def send_test_notification(
    payload: NotificationTestIn, current_user: CurrentUser
):
    result = await send_push_notification(
        token=payload.token,
        title=payload.title,
        body=payload.body,
        data=payload.data,
    )
    return result
