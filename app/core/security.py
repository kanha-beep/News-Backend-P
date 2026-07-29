from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe

import jwt
from fastapi import Depends, Header, Request, Response
from jwt import InvalidTokenError

from app.core.config import Settings, get_settings
from app.core.exceptions import AppError
from app.models.collections import object_id, users_collection


def extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    if not authorization.startswith("Bearer "):
        return None
    token = authorization[7:].strip()
    return token or None


def create_token(user: dict, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    payload = {
        "sub": str(user["_id"]),
        "email": user.get("email", ""),
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def decode_token(token: str, settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])


def get_cookie_token(request: Request, settings: Settings | None = None) -> str | None:
    settings = settings or get_settings()
    token = request.cookies.get(settings.AUTH_COOKIE_NAME, "").strip()
    return token or None


def get_session_user_id(request: Request) -> str | None:
    session = getattr(request, "session", None) or {}
    user_id = str(session.get("user_id", "")).strip()
    return user_id or None


def extract_request_token(request: Request, authorization: str | None, settings: Settings | None = None) -> str | None:
    settings = settings or get_settings()
    return (
        extract_bearer_token(authorization)
        or get_cookie_token(request, settings)
        or get_session_user_id(request)
    )


def issue_csrf_token() -> str:
    return token_urlsafe(32)


def apply_auth_cookies(response: Response, token: str, csrf_token: str, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    secure = settings.is_production
    response.set_cookie(
        key=settings.AUTH_COOKIE_NAME,
        value=token,
        max_age=settings.COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        key=settings.CSRF_COOKIE_NAME,
        value=csrf_token,
        max_age=settings.COOKIE_MAX_AGE_SECONDS,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
    )


def apply_csrf_cookie(response: Response, csrf_token: str, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    response.set_cookie(
        key=settings.CSRF_COOKIE_NAME,
        value=csrf_token,
        max_age=settings.COOKIE_MAX_AGE_SECONDS,
        httponly=False,
        secure=settings.is_production,
        samesite="lax",
        path="/",
    )


def clear_auth_cookies(response: Response, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    response.delete_cookie(settings.AUTH_COOKIE_NAME, path="/")
    response.delete_cookie(settings.CSRF_COOKIE_NAME, path="/")


def get_optional_user(request: Request, authorization: str | None = Header(default=None)) -> dict | None:
    token = extract_request_token(request, authorization)
    if not token:
        return None

    try:
        if get_session_user_id(request) and token == get_session_user_id(request):
            user = users_collection().find_one({"_id": object_id(token)})
        else:
            payload = decode_token(token)
            user = users_collection().find_one({"_id": object_id(payload.get("sub"))})
        if not user:
            return None
        return user
    except InvalidTokenError:
        return None
    except Exception:
        return None


def get_current_user(request: Request, authorization: str | None = Header(default=None)) -> dict:
    token = extract_request_token(request, authorization)
    if not token:
        raise AppError("Authentication required", status_code=401, public_message="Authentication required")

    try:
        if get_session_user_id(request) and token == get_session_user_id(request):
            user = users_collection().find_one({"_id": object_id(token)})
            if not user:
                raise AppError("Invalid session", status_code=401, public_message="Invalid session")
            return user
        payload = decode_token(token)
    except InvalidTokenError:
        raise AppError("Invalid token", status_code=401, public_message="Invalid token")
    except Exception:
        raise AppError("Invalid token", status_code=401, public_message="Invalid token")

    user = users_collection().find_one({"_id": object_id(payload.get("sub"))})
    if not user:
        raise AppError("Invalid token", status_code=401, public_message="Invalid token")
    return user


CurrentUser = Depends(get_current_user)
OptionalUser = Depends(get_optional_user)
