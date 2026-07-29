from pydantic import BaseModel


class CommentCreatePayload(BaseModel):
    link: str
    content: str

