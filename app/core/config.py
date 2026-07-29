from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[2] / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    MONGO_URI: str
    JWT_SECRET: str
    PORT: int
    ENVIRONMENT: str = "development"
    MAX_REQUEST_SIZE_BYTES: int = 1_048_576
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    RATE_LIMIT_MAX_REQUESTS: int = 120
    RATE_LIMIT_AUTH_MAX_REQUESTS: int = 20
    SESSION_SECRET: str = ""
    SESSION_COOKIE_NAME: str = "news_session"
    AUTH_COOKIE_NAME: str = "news_access_token"
    CSRF_COOKIE_NAME: str = "news_csrf_token"
    CSRF_HEADER_NAME: str = "x-csrf-token"
    COOKIE_MAX_AGE_SECONDS: int = 60 * 60 * 24 * 7
    UPLOAD_DIR: str = "uploads"
    UPLOAD_MAX_FILE_SIZE_BYTES: int = 5 * 1024 * 1024

    FRONT_END_URI: str = ""
    BLOG_FRONT_END_URI: str = "https://blogs-frontend-omega.vercel.app"
    BLOGS_MONGO_URI: str = ""
    RUST_RSS_FETCHER_BIN: str = ""
    HINDU_HOME_RSS: str = "https://www.thehindu.com/feeder/default.rss"
    NEWS_SYNC_CRON: str = "*/10 * * * *"
    PUSH_VAPID_PUBLIC_KEY: str = ""
    PUSH_VAPID_PRIVATE_KEY: str = ""
    PUSH_VAPID_SUBJECT: str = ""
    ALLOWED_ORIGINS_RAW: str = Field(default="", alias="FRONT_END_URI")
    TRUSTED_HOSTS_RAW: str = ""

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS_RAW.split(",") if origin.strip()]

    @property
    def trusted_hosts(self) -> list[str]:
        configured_hosts = [host.strip() for host in self.TRUSTED_HOSTS_RAW.split(",") if host.strip()]
        origin_hosts = []
        for origin in self.allowed_origins:
            parsed = urlparse(origin)
            if parsed.hostname:
                origin_hosts.append(parsed.hostname)
        return list(dict.fromkeys(configured_hosts + origin_hosts + ["localhost", "127.0.0.1"]))

    @property
    def push_enabled(self) -> bool:
        return bool(
            self.PUSH_VAPID_PUBLIC_KEY
            and self.PUSH_VAPID_PRIVATE_KEY
            and self.PUSH_VAPID_SUBJECT
        )

    @property
    def session_secret(self) -> str:
        return self.SESSION_SECRET or self.JWT_SECRET

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.strip().lower() == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    insecure_secrets = {
        "change-me-in-env",
        "replace-with-a-long-random-secret",
        "changeme",
        "secret",
    }
    if settings.JWT_SECRET.strip().lower() in insecure_secrets or len(settings.JWT_SECRET.strip()) < 32:
        raise RuntimeError("JWT_SECRET must be set to a strong secret value with at least 32 characters.")
    if settings.PORT <= 0:
        raise RuntimeError("PORT must be a valid positive integer.")
    if settings.MAX_REQUEST_SIZE_BYTES <= 0:
        raise RuntimeError("MAX_REQUEST_SIZE_BYTES must be a valid positive integer.")
    if settings.RATE_LIMIT_WINDOW_SECONDS <= 0:
        raise RuntimeError("RATE_LIMIT_WINDOW_SECONDS must be a valid positive integer.")
    if settings.RATE_LIMIT_MAX_REQUESTS <= 0 or settings.RATE_LIMIT_AUTH_MAX_REQUESTS <= 0:
        raise RuntimeError("Rate limit thresholds must be valid positive integers.")
    if settings.COOKIE_MAX_AGE_SECONDS <= 0:
        raise RuntimeError("COOKIE_MAX_AGE_SECONDS must be a valid positive integer.")
    if settings.UPLOAD_MAX_FILE_SIZE_BYTES <= 0:
        raise RuntimeError("UPLOAD_MAX_FILE_SIZE_BYTES must be a valid positive integer.")
    return settings
