from pathlib import Path
import secrets

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from blogapi.config import config
from blogapi.models.me import ImageUploadOut
from blogapi.security import get_current_user

router = APIRouter(prefix="/uploads", tags=["uploads"])

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def _looks_like_declared_image(content_type: str, data: bytes) -> bool:
    if content_type == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/webp":
        return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    if content_type == "image/gif":
        return data.startswith((b"GIF87a", b"GIF89a"))
    return False


def _upload_dir() -> Path:
    path = Path(config.upload_dir)
    if not path.is_absolute():
        path = Path.cwd() / path
    path.mkdir(parents=True, exist_ok=True)
    return path


@router.post(
    "/images",
    response_model=ImageUploadOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_current_user)],
)
async def upload_image(file: UploadFile = File(...)):
    content_type = file.content_type or ""
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported image content type",
        )

    data = await file.read(config.max_image_upload_bytes + 1)
    size = len(data)
    if size == 0:
        raise HTTPException(status_code=400, detail="Uploaded image is empty")
    if size > config.max_image_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Uploaded image is too large",
        )
    if not _looks_like_declared_image(content_type, data):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file does not match declared image content type",
        )

    extension = ALLOWED_IMAGE_TYPES[content_type]
    filename = f"{secrets.token_urlsafe(18)}{extension}"
    destination = _upload_dir() / filename
    destination.write_bytes(data)

    return {
        "url": f"{config.upload_url_prefix.rstrip('/')}/{filename}",
        "filename": filename,
        "content_type": content_type,
        "size": size,
    }
