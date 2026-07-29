from pydantic import BaseModel


class AuthPayload(BaseModel):
    name: str | None = None
    email: str
    password: str

