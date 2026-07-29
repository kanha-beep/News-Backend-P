from fastapi import APIRouter

from app.core.security import CurrentUser
from app.schemas.comments import CommentCreatePayload
from app.services.comments import create_comment, list_comments


router = APIRouter(prefix="/api/comments", tags=["comments"])


@router.get("")
@router.get("/")
def get_comments(link: str):
    return {"items": list_comments(link)}


@router.post("", status_code=201)
@router.post("/", status_code=201)
def add_comment(payload: CommentCreatePayload, user=CurrentUser):
    return {"item": create_comment(link=payload.link, content=payload.content, user=user)}
