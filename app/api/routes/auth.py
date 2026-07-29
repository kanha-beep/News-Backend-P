from fastapi import APIRouter, Request, Response

from app.core.security import CurrentUser, apply_auth_cookies, apply_csrf_cookie, clear_auth_cookies, issue_csrf_token
from app.schemas.auth import AuthPayload
from app.services.auth import ensure_user_has_name, login_user, register_user, sanitize_user


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", status_code=201)
def register(payload: AuthPayload, request: Request, response: Response):
    result = register_user(payload.model_dump())
    apply_auth_cookies(response, result["token"], result["csrfToken"])
    request.session["user_id"] = result["user"]["id"]
    return result


@router.post("/login")
def login(payload: AuthPayload, request: Request, response: Response):
    result = login_user(payload.model_dump())
    apply_auth_cookies(response, result["token"], result["csrfToken"])
    request.session["user_id"] = result["user"]["id"]
    return result


@router.post("/logout")
def logout(request: Request, response: Response):
    request.session.clear()
    clear_auth_cookies(response)
    return {"ok": True}


@router.get("/csrf-token")
def get_csrf_token(response: Response):
    csrf_token = issue_csrf_token()
    apply_csrf_cookie(response, csrf_token)
    return {"csrfToken": csrf_token}


@router.get("/me")
def get_current_user_route(user=CurrentUser):
    return {"user": sanitize_user(ensure_user_has_name(user))}
