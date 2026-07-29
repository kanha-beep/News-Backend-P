import bcrypt

from app.core.exceptions import bad_request
from app.core.security import create_token, issue_csrf_token
from app.models.collections import users_collection
from app.utils.validation import read_string


def build_fallback_name(email: str = "") -> str:
    local_part = str(email).split("@")[0].strip()
    return local_part or "Writer"


def ensure_user_has_name(user: dict | None, preferred_name: str = "") -> dict | None:
    if not user:
        return user

    next_name = read_string(preferred_name, "Name", max_length=80) or user.get("name") or build_fallback_name(user.get("email", ""))
    if user.get("name") != next_name:
        users_collection().update_one({"_id": user["_id"]}, {"$set": {"name": next_name}})
        user["name"] = next_name
    return user


def sanitize_user(user: dict) -> dict:
    return {
        "id": str(user["_id"]),
        "name": user.get("name", ""),
        "email": user.get("email", ""),
        "favoriteCount": len(user.get("favoriteLinks", []) or []),
        "likedCount": len(user.get("likedLinks", []) or []),
        "dislikedCount": len(user.get("dislikedLinks", []) or []),
    }


def register_user(payload: dict) -> dict:
    raw_name = read_string(payload.get("name"), "Name", max_length=80)
    email = read_string(payload.get("email"), "Email", required=True, max_length=200, lowercase=True)
    password = read_string(payload.get("password"), "Password", required=True, min_length=6, max_length=200)

    if users_collection().find_one({"email": email}):
        raise bad_request("User already exists")

    name = raw_name or build_fallback_name(email)
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user = {
        "name": name,
        "email": email,
        "passwordHash": password_hash,
        "favoriteLinks": [],
        "likedLinks": [],
        "dislikedLinks": [],
    }
    result = users_collection().insert_one(user)
    user["_id"] = result.inserted_id
    return {"token": create_token(user), "csrfToken": issue_csrf_token(), "user": sanitize_user(user)}


def login_user(payload: dict) -> dict:
    email = read_string(payload.get("email"), "Email", required=True, max_length=200, lowercase=True)
    password = read_string(payload.get("password"), "Password", required=True, max_length=200)
    user = users_collection().find_one({"email": email})
    if not user:
        raise bad_request("Invalid credentials")

    if not bcrypt.checkpw(password.encode("utf-8"), user.get("passwordHash", "").encode("utf-8")):
        raise bad_request("Invalid credentials")

    ensure_user_has_name(user)
    return {"token": create_token(user), "csrfToken": issue_csrf_token(), "user": sanitize_user(user)}
