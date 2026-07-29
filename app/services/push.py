import json
from datetime import datetime, timezone

from pymongo import ReturnDocument
from pywebpush import WebPushException, webpush

from app.core.config import get_settings
from app.core.exceptions import bad_request
from app.models.collections import alert_subscriptions_collection, push_subscriptions_collection
from app.utils.serialization import serialize_document


def create_notification_payload(*, title: str, body: str, url: str) -> str:
    return json.dumps(
        {
            "title": title,
            "body": body,
            "url": url,
            "icon": "/lightning-news-logo.png",
            "badge": "/lightning-news-logo.png",
        }
    )


def build_alert_url() -> str:
    settings = get_settings()
    base_url = settings.allowed_origins[0] if settings.allowed_origins else settings.FRONT_END_URI
    return f"{base_url.rstrip('/')}/?view=alerts" if base_url else "/"


def article_has_matching_tag(article: dict, alert_tag: str) -> bool:
    return alert_tag in [str(tag or "").strip().lower() for tag in article.get("tags", [])]


def get_push_public_key() -> str:
    return get_settings().PUSH_VAPID_PUBLIC_KEY


def is_push_enabled() -> bool:
    return get_settings().push_enabled


def list_user_push_subscriptions(user_id) -> list[dict]:
    cursor = push_subscriptions_collection().find({"user": user_id, "isActive": True})
    return [serialize_document(item) for item in cursor]


def save_push_subscription(*, user_id, subscription: dict, user_agent: str) -> dict:
    settings = get_settings()
    if not settings.push_enabled:
        raise bad_request("Push notifications are not configured on the server")

    endpoint = (subscription.get("endpoint") or "").strip()
    keys = subscription.get("keys") or {}
    p256dh = (keys.get("p256dh") or "").strip()
    auth = (keys.get("auth") or "").strip()
    if not endpoint or not p256dh or not auth:
        raise bad_request("Invalid push subscription payload")

    document = push_subscriptions_collection().find_one_and_update(
        {"endpoint": endpoint},
        {
            "$set": {
                "user": user_id,
                "endpoint": endpoint,
                "expirationTime": subscription.get("expirationTime"),
                "keys": {"p256dh": p256dh, "auth": auth},
                "userAgent": user_agent or "",
                "isActive": True,
                "updatedAt": datetime.now(timezone.utc),
            },
            "$setOnInsert": {
                "createdAt": datetime.now(timezone.utc),
                "lastNotifiedAt": None,
            },
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return serialize_document(document)


def remove_push_subscription(*, user_id, endpoint: str) -> None:
    settings = get_settings()
    if not settings.push_enabled:
        return
    if not endpoint or not endpoint.strip():
        raise bad_request("Push endpoint is required")
    push_subscriptions_collection().update_one(
        {"user": user_id, "endpoint": endpoint.strip()},
        {"$set": {"isActive": False, "updatedAt": datetime.now(timezone.utc)}},
    )


def send_push_to_subscriptions(subscriptions: list[dict], payload: dict) -> list[dict]:
    settings = get_settings()
    if not settings.push_enabled or not subscriptions:
        return []

    results = []
    for subscription_doc in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": subscription_doc["endpoint"],
                    "keys": subscription_doc["keys"],
                },
                data=create_notification_payload(**payload),
                vapid_private_key=settings.PUSH_VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.PUSH_VAPID_SUBJECT},
            )
            push_subscriptions_collection().update_one(
                {"_id": subscription_doc["_id"]},
                {"$set": {"lastNotifiedAt": datetime.now(timezone.utc), "isActive": True}},
            )
            results.append({"ok": True, "endpoint": subscription_doc["endpoint"]})
        except WebPushException as error:
            status_code = getattr(error.response, "status_code", None) if getattr(error, "response", None) else None
            if status_code in {404, 410}:
                push_subscriptions_collection().update_one({"_id": subscription_doc["_id"]}, {"$set": {"isActive": False}})
            results.append(
                {
                    "ok": False,
                    "endpoint": subscription_doc["endpoint"],
                    "statusCode": status_code,
                    "message": str(error),
                }
            )
    return results


def send_welcome_push_notification(user_id) -> None:
    if not is_push_enabled():
        return
    subscriptions = list(push_subscriptions_collection().find({"user": user_id, "isActive": True}))
    if not subscriptions:
        return
    send_push_to_subscriptions(
        subscriptions,
        {
            "title": "Lightning News alerts enabled",
            "body": "You will now receive push notifications for new matches on saved alerts.",
            "url": build_alert_url(),
        },
    )


def send_test_push_notification(user_id) -> dict:
    if not is_push_enabled():
        raise bad_request("Push notifications are not configured on the server")
    subscriptions = list(push_subscriptions_collection().find({"user": user_id, "isActive": True}))
    if not subscriptions:
        raise bad_request("Enable push notifications in this browser first")
    results = send_push_to_subscriptions(
        subscriptions,
        {
            "title": "Lightning News test notification",
            "body": "Push delivery is working for this browser.",
            "url": build_alert_url(),
        },
    )
    success_count = len([item for item in results if item.get("ok")])
    if success_count == 0:
        first_failure = next((item for item in results if not item.get("ok")), None)
        if first_failure and first_failure.get("statusCode"):
            raise bad_request(f"Push delivery failed ({first_failure['statusCode']}). Check server logs for details.")
        raise bad_request("Push delivery failed. Check server logs for details.")
    return {"ok": True, "sent": success_count, "total": len(results)}


def notify_users_about_matching_articles(articles: list[dict]) -> None:
    if not is_push_enabled() or not articles:
        return
    alerts = list(alert_subscriptions_collection().find({"enabled": True}))
    subscriptions = list(push_subscriptions_collection().find({"isActive": True}))

    subscriptions_by_user = {}
    for subscription in subscriptions:
        subscriptions_by_user.setdefault(str(subscription["user"]), []).append(subscription)

    notifications_by_user = {}
    for alert in alerts:
        matches = [article for article in articles if article_has_matching_tag(article, str(alert.get("topic", "")).lower())]
        if not matches:
            continue
        state = notifications_by_user.setdefault(str(alert["user"]), {"topics": set(), "matches": []})
        state["topics"].add(alert.get("topic"))
        state["matches"].extend(matches)

    for user_id, state in notifications_by_user.items():
        user_subscriptions = subscriptions_by_user.get(user_id, [])
        if not user_subscriptions:
            continue
        unique_matches = list({item["link"]: item for item in state["matches"]}.values())
        topics = list(state["topics"])
        first_article = unique_matches[0] if unique_matches else {}
        title = f"{len(unique_matches)} new alert matches" if len(unique_matches) > 1 else f"New match for {topics[0]}"
        body = (
            f"{', '.join(topics)}: {first_article.get('title', 'New stories available')}"
            if len(unique_matches) > 1
            else first_article.get("title", "A saved alert has a new matching story.")
        )
        send_push_to_subscriptions(
            user_subscriptions,
            {
                "title": title,
                "body": body,
                "url": build_alert_url(),
            },
        )
