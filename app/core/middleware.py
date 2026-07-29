import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")

        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        if proto == "https":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_body_size: int):
        super().__init__(app)
        self.max_body_size = max_body_size

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit() and int(content_length) > self.max_body_size:
            return JSONResponse(
                status_code=413,
                content={"error": "Request body too large", "message": "Request body too large"},
            )

        if request.method in {"POST", "PUT", "PATCH"}:
            body = await request.body()
            if len(body) > self.max_body_size:
                return JSONResponse(
                    status_code=413,
                    content={"error": "Request body too large", "message": "Request body too large"},
                )

        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.settings = get_settings()
        self.request_log: dict[str, deque[float]] = defaultdict(deque)

    def _get_client_ip(self, request: Request) -> str:
        forwarded_for = request.headers.get("x-forwarded-for", "")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        if request.client and request.client.host:
            return request.client.host
        return "unknown"

    def _get_limit(self, path: str) -> int:
        if path.startswith("/api/auth/"):
            return self.settings.RATE_LIMIT_AUTH_MAX_REQUESTS
        return self.settings.RATE_LIMIT_MAX_REQUESTS

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS" or request.url.path in {"/api/health", "/docs", "/openapi.json"}:
            return await call_next(request)

        now = time.time()
        window_start = now - self.settings.RATE_LIMIT_WINDOW_SECONDS
        key = f"{self._get_client_ip(request)}:{request.url.path}"
        entries = self.request_log[key]

        while entries and entries[0] < window_start:
            entries.popleft()

        limit = self._get_limit(request.url.path)
        if len(entries) >= limit:
            retry_after = max(1, int(entries[0] + self.settings.RATE_LIMIT_WINDOW_SECONDS - now))
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(retry_after)},
                content={
                    "error": "Too many requests",
                    "message": "Rate limit exceeded. Please retry shortly.",
                },
            )

        entries.append(now)
        response = await call_next(request)
        response.headers.setdefault("X-RateLimit-Limit", str(limit))
        response.headers.setdefault("X-RateLimit-Remaining", str(max(0, limit - len(entries))))
        response.headers.setdefault("X-RateLimit-Window", str(self.settings.RATE_LIMIT_WINDOW_SECONDS))
        return response


class CSRFMiddleware(BaseHTTPMiddleware):
    EXEMPT_PATHS = {
        "/api/auth/login",
        "/api/auth/register",
        "/api/auth/logout",
        "/api/health",
    }

    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        if request.method in {"GET", "HEAD", "OPTIONS"} or request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        authorization = request.headers.get("authorization", "")
        if authorization.startswith("Bearer "):
            return await call_next(request)

        auth_cookie = request.cookies.get(settings.AUTH_COOKIE_NAME, "").strip()
        if not auth_cookie:
            return await call_next(request)

        csrf_cookie = request.cookies.get(settings.CSRF_COOKIE_NAME, "").strip()
        csrf_header = request.headers.get(settings.CSRF_HEADER_NAME, "").strip()
        if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
            return JSONResponse(
                status_code=403,
                content={
                    "error": "CSRF validation failed",
                    "message": "Missing or invalid CSRF token",
                },
            )

        return await call_next(request)
