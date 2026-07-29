from fastapi import APIRouter, Request

from app.core.exceptions import bad_request
from app.core.security import CurrentUser
from app.schemas.push import PushSubscribePayload, PushUnsubscribePayload
from app.services.push import (
    get_push_public_key,
    is_push_enabled,
    list_user_push_subscriptions,
    remove_push_subscription,
    save_push_subscription,
    send_test_push_notification,
    send_welcome_push_notification,
)


router = APIRouter(prefix="/api/push", tags=["push"])


@router.get("/public-key")
def get_public_key():
    if not is_push_enabled():
        raise bad_request("Push notifications are not configured")
    return {"publicKey": get_push_public_key()}


@router.get("/subscriptions")
def get_subscriptions(user=CurrentUser):
    return {"items": list_user_push_subscriptions(user["_id"])}


@router.post("/subscribe", status_code=201)
def subscribe(payload: PushSubscribePayload, request: Request, user=CurrentUser):
    item = save_push_subscription(
        user_id=user["_id"],
        subscription=payload.subscription.model_dump(),
        user_agent=request.headers.get("user-agent", ""),
    )
    send_welcome_push_notification(user["_id"])
    return {"item": item}


@router.post("/unsubscribe")
def unsubscribe(payload: PushUnsubscribePayload, user=CurrentUser):
    remove_push_subscription(user_id=user["_id"], endpoint=payload.endpoint)
    return {"ok": True}


@router.post("/send-test")
def send_test(user=CurrentUser):
    return send_test_push_notification(user["_id"])

