from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument

from app.core.exceptions import bad_request
from app.models.collections import blog_drafts_collection, news_collection
from app.utils.news_intelligence import build_neutral_summary
from app.utils.serialization import serialize_document


def list_drafts(user_id) -> list[dict]:
    cursor = blog_drafts_collection().find({"user": user_id}).sort("updatedAt", -1)
    return [serialize_document(item) for item in cursor]


def create_draft_from_article(*, article_link: str, notes: str | None, user: dict) -> dict:
    normalized_link = (article_link or "").strip()
    if not normalized_link:
        raise bad_request("Article link is required")

    article = news_collection().find_one({"link": normalized_link})
    if not article:
        raise bad_request("Article not found")

    summary = build_neutral_summary([article])
    draft = {
        "user": user["_id"],
        "sourceArticleLink": article.get("link"),
        "sourceArticleTitle": article.get("title", ""),
        "headline": f"Perspective: {article.get('title', '')}",
        "summary": summary,
        "notes": (notes or "").strip(),
        "content": "\n".join(
            [
                "## Why this story matters",
                summary,
                "",
                "## What happened",
                article.get("description") or article.get("title", ""),
                "",
                "## Your angle",
                "Add your reporting, analysis, or first-person perspective here.",
            ]
        ),
        "status": "draft",
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc),
    }
    result = blog_drafts_collection().insert_one(draft)
    draft["_id"] = result.inserted_id
    return serialize_document(draft)


def update_draft(draft_id: str, payload: dict, user_id) -> dict:
    if not ObjectId.is_valid(draft_id):
        raise bad_request("Invalid draft id")
    update_fields = {"updatedAt": datetime.now(timezone.utc)}
    for field in ("headline", "summary", "notes", "content", "status"):
        if isinstance(payload.get(field), str):
            update_fields[field] = payload[field].strip() if field != "content" else payload[field]
    draft = blog_drafts_collection().find_one_and_update(
        {"_id": ObjectId(draft_id), "user": user_id},
        {"$set": update_fields},
        return_document=ReturnDocument.AFTER,
    )
    if not draft:
        raise bad_request("Draft not found")
    return serialize_document(draft)
