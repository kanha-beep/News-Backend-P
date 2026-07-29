from fastapi import APIRouter
from pymongo import ReturnDocument

from app.api.deps import OptionalUser
from app.core.exceptions import AppError, bad_request
from app.schemas.news import ArticleTogglePayload
from app.services.auth import sanitize_user
from app.services.news import get_available_tags, sync_news_from_rss, upsert_article_if_missing
from app.models.collections import users_collection


router = APIRouter(prefix="/api", tags=["legacy"])


@router.get("/hindu")
def get_legacy_hindu(rssUrl: str | None = None):
    return sync_news_from_rss(rssUrl)


@router.get("/tags")
def get_legacy_tags():
    return {"items": get_available_tags()}


def _require_legacy_auth(user):
    if not user:
        raise AppError("Authentication required", status_code=401, public_message="Authentication required")


def _toggle_legacy_link_array(user: dict, field_name: str, link: str, opposite_field: str | None = None) -> dict:
    current_values = user.get(field_name, []) or []
    already_selected = link in current_values
    update = {"$pull" if already_selected else "$addToSet": {field_name: link}}
    if not already_selected and opposite_field:
        update.setdefault("$pull", {})[opposite_field] = link
    updated_user = users_collection().find_one_and_update(
        {"_id": user["_id"]},
        update,
        return_document=ReturnDocument.AFTER,
    )
    return {"user": updated_user, "alreadySelected": already_selected}


@router.post("/favorites/toggle")
def toggle_legacy_favorite(payload: ArticleTogglePayload, user=OptionalUser):
    _require_legacy_auth(user)
    if not payload.link:
        raise bad_request("Link is required")
    upsert_article_if_missing(payload.model_dump())
    result = _toggle_legacy_link_array(user, "favoriteLinks", payload.link)
    return {"favorite": not result["alreadySelected"], "user": sanitize_user(result["user"])}


@router.post("/likes/toggle")
def toggle_legacy_like(payload: ArticleTogglePayload, user=OptionalUser):
    _require_legacy_auth(user)
    if not payload.link:
        raise bad_request("Link is required")
    upsert_article_if_missing(payload.model_dump())
    result = _toggle_legacy_link_array(user, "likedLinks", payload.link, "dislikedLinks")
    return {"liked": not result["alreadySelected"], "disliked": False, "user": sanitize_user(result["user"])}


@router.post("/dislikes/toggle")
def toggle_legacy_dislike(payload: ArticleTogglePayload, user=OptionalUser):
    _require_legacy_auth(user)
    if not payload.link:
        raise bad_request("Link is required")
    upsert_article_if_missing(payload.model_dump())
    result = _toggle_legacy_link_array(user, "dislikedLinks", payload.link, "likedLinks")
    return {"liked": False, "disliked": not result["alreadySelected"], "user": sanitize_user(result["user"])}
