from pydantic import BaseModel


class VisitPayload(BaseModel):
    pageUrl: str | None = None
    path: str | None = None
    title: str | None = None
    referrer: str | None = None
    screen: str | None = None
    timezone: str | None = None
    language: str | None = None

