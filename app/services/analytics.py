from datetime import datetime, timezone

from app.models.collections import visits_collection
from app.utils.validation import read_string


def get_client_ip(headers: dict, fallback_ip: str = "") -> str:
    forwarded_for = headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    real_ip = headers.get("x-real-ip", "")
    if real_ip:
        return real_ip.strip()
    return fallback_ip


def infer_browser(user_agent: str = "") -> str:
    value = user_agent.lower()
    if "edg/" in value:
        return "Edge"
    if "chrome/" in value:
        return "Chrome"
    if "safari/" in value and "chrome/" not in value:
        return "Safari"
    if "firefox/" in value:
        return "Firefox"
    if "opr/" in value or "opera/" in value:
        return "Opera"
    return "Unknown"


def infer_os(user_agent: str = "") -> str:
    value = user_agent.lower()
    if "windows" in value:
        return "Windows"
    if "android" in value:
        return "Android"
    if "iphone" in value or "ipad" in value or "ios" in value:
        return "iOS"
    if "mac os" in value:
        return "macOS"
    if "linux" in value:
        return "Linux"
    return "Unknown"


def infer_device_type(user_agent: str = "") -> str:
    value = user_agent.lower()
    if "mobile" in value:
        return "Mobile"
    if "tablet" in value or "ipad" in value:
        return "Tablet"
    return "Desktop"


def record_visit(*, payload: dict, headers: dict, fallback_ip: str = "") -> None:
    user_agent = headers.get("user-agent", "")
    visits_collection().insert_one(
        {
            "pageUrl": read_string(payload.get("pageUrl"), "Page URL", max_length=700),
            "path": read_string(payload.get("path"), "Path", max_length=300),
            "title": read_string(payload.get("title"), "Title", max_length=200),
            "referrer": read_string(payload.get("referrer"), "Referrer", max_length=700),
            "ipAddress": get_client_ip(headers, fallback_ip),
            "userAgent": user_agent,
            "browser": infer_browser(user_agent),
            "deviceType": infer_device_type(user_agent),
            "os": infer_os(user_agent),
            "screen": read_string(payload.get("screen"), "Screen", max_length=50),
            "timezone": read_string(payload.get("timezone"), "Timezone", max_length=100),
            "language": read_string(payload.get("language"), "Language", max_length=50),
            "country": str(headers.get("x-vercel-ip-country", "") or headers.get("cf-ipcountry", "")),
            "region": str(headers.get("x-vercel-ip-country-region", "") or headers.get("x-appengine-region", "")),
            "city": str(headers.get("x-vercel-ip-city", "")),
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc),
        }
    )

