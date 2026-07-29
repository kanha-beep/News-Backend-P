from pydantic import BaseModel


class AlertCreatePayload(BaseModel):
    topic: str
    type: str


class AlertUpdatePayload(BaseModel):
    enabled: bool

