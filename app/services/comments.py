from datetime import datetime, timezone

from app.core.exceptions import bad_request
from app.models.collections import comments_collection
from app.utils.moderation import moderate_comment
from app.utils.validation import read_string


def list_comments(link: str) -> list[dict]:
    news_link = read_string(link, "Article link", required=True, max_length=600)
    cursor = comments_collection().find({"newsLink": news_link}).sort([("createdAt", -1), ("_id", -1)]).limit(100)
    return [
        {
            "id": str(comment["_id"]),
            "content": comment.get("content", ""),
            "userName": comment.get("userName", ""),
            "createdAt": comment.get("createdAt"),
            "moderationStatus": comment.get("moderationStatus", "approved"),
        }
        for comment in cursor
    ]


def create_comment(*, link: str, content: str, user: dict) -> dict:
    news_link = read_string(link, "Article link", required=True, max_length=600)
    normalized_content = read_string(content, "Comment", required=True, max_length=500)
    moderation = moderate_comment(normalized_content)
    if not moderation["accepted"]:
        raise bad_request(moderation["reason"])

    comment = {
        "newsLink": news_link,
        "content": normalized_content,
        "user": user["_id"],
        "userName": user.get("name") or user.get("email", ""),
        "moderationStatus": "approved",
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc),
    }
    result = comments_collection().insert_one(comment)
    comment["_id"] = result.inserted_id
    return {
        "id": str(comment["_id"]),
        "content": comment["content"],
        "userName": comment["userName"],
        "createdAt": comment["createdAt"],
        "moderationStatus": "approved",
    }

