from pydantic import BaseModel


class NewsFilterPayload(BaseModel):
    tag: str | None = None
    title: str | None = None
    date: str | None = None
    month: str | None = None
    page: int | None = None
    favoritesOnly: bool | None = None


class ArticleTogglePayload(BaseModel):
    link: str
    title: str | None = None
    description: str | None = None
    pubDate: str | None = None

