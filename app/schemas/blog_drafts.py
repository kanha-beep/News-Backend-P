from pydantic import BaseModel


class BlogDraftCreatePayload(BaseModel):
    articleLink: str
    notes: str | None = None


class BlogDraftUpdatePayload(BaseModel):
    headline: str | None = None
    summary: str | None = None
    notes: str | None = None
    content: str | None = None
    status: str | None = None

