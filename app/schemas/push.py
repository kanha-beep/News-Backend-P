from pydantic import BaseModel


class PushSubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionBody(BaseModel):
    endpoint: str
    expirationTime: str | None = None
    keys: PushSubscriptionKeys


class PushSubscribePayload(BaseModel):
    subscription: PushSubscriptionBody


class PushUnsubscribePayload(BaseModel):
    endpoint: str

