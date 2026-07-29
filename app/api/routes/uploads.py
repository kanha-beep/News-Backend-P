from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, UploadFile

from app.core.config import get_settings
from app.core.exceptions import bad_request
from app.core.security import CurrentUser


router = APIRouter(prefix="/api/uploads", tags=["uploads"])

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def _upload_root() -> Path:
    settings = get_settings()
    root = Path(__file__).resolve().parents[3] / settings.UPLOAD_DIR
    root.mkdir(parents=True, exist_ok=True)
    return root


@router.post("/image", status_code=201)
async def upload_image(file: UploadFile = File(...), user=CurrentUser):
    settings = get_settings()
    content_type = str(file.content_type or "").lower()
    extension = ALLOWED_IMAGE_TYPES.get(content_type)
    if not extension:
        raise bad_request("Unsupported file type")

    file_bytes = await file.read()
    if not file_bytes:
        raise bad_request("Uploaded file is empty")
    if len(file_bytes) > settings.UPLOAD_MAX_FILE_SIZE_BYTES:
        raise bad_request("Uploaded file is too large")

    user_dir = _upload_root() / str(user["_id"])
    user_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}{extension}"
    destination = user_dir / filename
    destination.write_bytes(file_bytes)

    return {
        "item": {
            "fileName": file.filename or filename,
            "storedName": filename,
            "contentType": content_type,
            "size": len(file_bytes),
            "url": f"/uploads/{user['_id']}/{filename}",
        }
    }
