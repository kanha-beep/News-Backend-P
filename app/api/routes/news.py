from fastapi import APIRouter
from pymongo import ReturnDocument

from app.api.deps import OptionalUser
from app.core.exceptions import bad_request
from app.core.security import CurrentUser
from app.schemas.news import ArticleTogglePayload, NewsFilterPayload
from app.services.auth import sanitize_user
from app.services.news import (
    get_article_by_link,
    get_available_tags,
    get_paginated_news,
    sync_news_from_rss,
    upsert_article_if_missing,
)
from app.models.collections import users_collection


router = APIRouter(prefix="/api/news", tags=["news"])


@router.get("/sync")
def sync_news(rssUrl: str | None = None):
    return sync_news_from_rss(rssUrl)


@router.get("")
@router.get("/")
def list_news(
    tag: str | None = None,
    title: str | None = None,
    date: str | None = None,
    month: str | None = None,
    page: int | None = None,
    favoritesOnly: str | None = None,
    user=OptionalUser,
):
    return get_paginated_news(
        tag=tag,
        title=title,
        date=date,
        month=month,
        page=page,
        favorite_links=(user or {}).get("favoriteLinks", []) if favoritesOnly == "true" else None,
        user_favorite_links=(user or {}).get("favoriteLinks", []),
        user_liked_links=(user or {}).get("likedLinks", []),
        user_disliked_links=(user or {}).get("dislikedLinks", []),
    )


@router.get("/article")
def get_article(link: str, user=OptionalUser):
    article = get_article_by_link(
        link=link,
        user_favorite_links=(user or {}).get("favoriteLinks", []),
        user_liked_links=(user or {}).get("likedLinks", []),
        user_disliked_links=(user or {}).get("dislikedLinks", []),
    )
    if not article:
        raise bad_request("Article not found")
    return {"item": article}


@router.post("/filter")
def filter_news(payload: NewsFilterPayload, user=OptionalUser):
    data = payload.model_dump()
    return get_paginated_news(
        tag=data.get("tag"),
        title=data.get("title"),
        date=data.get("date"),
        month=data.get("month"),
        page=data.get("page"),
        favorite_links=(user or {}).get("favoriteLinks", []) if data.get("favoritesOnly") else None,
        user_favorite_links=(user or {}).get("favoriteLinks", []),
        user_liked_links=(user or {}).get("likedLinks", []),
        user_disliked_links=(user or {}).get("dislikedLinks", []),
    )


@router.get("/tags")
def list_tags():
    return {"items": get_available_tags()}


def _toggle_user_link_array(user: dict, field_name: str, link: str, opposite_field: str | None = None) -> dict:
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
def toggle_favorite(payload: ArticleTogglePayload, user=CurrentUser):
    if not payload.link:
        raise bad_request("Link is required")
    upsert_article_if_missing(payload.model_dump())
    result = _toggle_user_link_array(user, "favoriteLinks", payload.link)
    return {"favorite": not result["alreadySelected"], "user": sanitize_user(result["user"])}


@router.post("/likes/toggle")
def toggle_like(payload: ArticleTogglePayload, user=CurrentUser):
    if not payload.link:
        raise bad_request("Link is required")
    upsert_article_if_missing(payload.model_dump())
    result = _toggle_user_link_array(user, "likedLinks", payload.link, "dislikedLinks")
    return {"liked": not result["alreadySelected"], "disliked": False, "user": sanitize_user(result["user"])}


@router.post("/dislikes/toggle")
def toggle_dislike(payload: ArticleTogglePayload, user=CurrentUser):
    if not payload.link:
        raise bad_request("Link is required")
    upsert_article_if_missing(payload.model_dump())
    result = _toggle_user_link_array(user, "dislikedLinks", payload.link, "likedLinks")
    return {"liked": False, "disliked": not result["alreadySelected"], "user": sanitize_user(result["user"])}


@router.get("/legacy-hindu")
def get_legacy_hindu_feed():
    return sync_news_from_rss()
