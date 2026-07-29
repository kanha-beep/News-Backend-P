from fastapi import APIRouter

from app.core.security import CurrentUser
from app.schemas.blog_drafts import BlogDraftCreatePayload, BlogDraftUpdatePayload
from app.services.blog_drafts import create_draft_from_article, list_drafts, update_draft


router = APIRouter(prefix="/api/blog-drafts", tags=["blog-drafts"])


@router.get("")
@router.get("/")
def get_drafts(user=CurrentUser):
    return {"items": list_drafts(user["_id"])}


@router.post("", status_code=201)
@router.post("/", status_code=201)
def create_draft(payload: BlogDraftCreatePayload, user=CurrentUser):
    return {
        "item": create_draft_from_article(
            article_link=payload.articleLink,
            notes=payload.notes,
            user=user,
        )
    }


@router.patch("/{draft_id}")
def patch_draft(draft_id: str, payload: BlogDraftUpdatePayload, user=CurrentUser):
    return {"item": update_draft(draft_id, payload.model_dump(exclude_none=True), user["_id"])}
