from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument

from app.core.exceptions import bad_request
from app.models.collections import alert_subscriptions_collection, news_collection
from app.utils.serialization import serialize_document
from app.utils.validation import read_optional_boolean, read_string


def normalize_alert_tag(value) -> str:
    return read_string(value, "Topic", required=True, max_length=120).lower()


def article_has_matching_tag(article: dict, alert_tag: str) -> bool:
    return alert_tag in [str(tag or "").strip().lower() for tag in article.get("tags", [])]


def list_alerts(user_id) -> list[dict]:
    cursor = alert_subscriptions_collection().find({"user": user_id}).sort("createdAt", -1)
    return [serialize_document(item) for item in cursor]


def create_alert(payload: dict, user_id) -> dict:
    alert_type = read_string(payload.get("type"), "Alert type", required=True, max_length=40).lower()
    topic = normalize_alert_tag(payload.get("topic"))
    if alert_type not in {"topic", "breaking"}:
        raise bad_request("Alert type must be topic or breaking")

    document = {
        "user": user_id,
        "type": alert_type,
        "topic": topic,
        "keywords": [topic],
        "enabled": True,
        "lastTriggeredAt": None,
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc),
    }
    result = alert_subscriptions_collection().insert_one(document)
    document["_id"] = result.inserted_id
    return serialize_document(document)


def toggle_alert(alert_id: str, enabled, user_id) -> dict:
    if not ObjectId.is_valid(alert_id):
        raise bad_request("Invalid alert id")
    alert = alert_subscriptions_collection().find_one_and_update(
        {"_id": ObjectId(alert_id), "user": user_id},
        {"$set": {"enabled": read_optional_boolean(enabled), "updatedAt": datetime.now(timezone.utc)}},
        return_document=ReturnDocument.AFTER,
    )
    if not alert:
        raise bad_request("Alert not found")
    return serialize_document(alert)


def delete_alert(alert_id: str, user_id) -> dict:
    if not ObjectId.is_valid(alert_id):
        raise bad_request("Invalid alert id")
    alert = alert_subscriptions_collection().find_one_and_delete({"_id": ObjectId(alert_id), "user": user_id})
    if not alert:
        raise bad_request("Alert not found")
    return serialize_document(alert)


def check_alerts(user_id) -> list[dict]:
    alerts = list(alert_subscriptions_collection().find({"user": user_id}).sort("createdAt", -1))
    recent_articles = list(news_collection().find({}).sort([("publishedAt", -1), ("createdAt", -1)]).limit(100))
    shaped = []
    for alert in alerts:
        topic = str(alert.get("topic", "")).lower()
        matches = [article for article in recent_articles if alert.get("enabled") and article_has_matching_tag(article, topic)]
        shaped.append(
            serialize_document(
                {
                    **alert,
                    "matchCount": len(matches),
                    "latestMatch": matches[0] if matches else None,
                    "matches": [
                        {
                            "title": article.get("title"),
                            "link": article.get("link"),
                            "pubDate": article.get("pubDate"),
                            "sourceName": article.get("sourceName"),
                        }
                        for article in matches[:3]
                    ],
                }
            )
        )
    return shaped
