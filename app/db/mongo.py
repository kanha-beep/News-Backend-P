from urllib.parse import urlparse, urlunparse

from pymongo import MongoClient

from app.core.config import get_settings


class MongoManager:
    def __init__(self) -> None:
        self.client: MongoClient | None = None
        self.db = None
        self.blogs_client: MongoClient | None = None
        self.blogs_db = None

    def connect(self) -> None:
        settings = get_settings()
        self.client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=10000)
        self.db = self.client.get_default_database()
        if self.db is None:
            parsed = urlparse(settings.MONGO_URI)
            db_name = parsed.path.lstrip("/") or "test"
            self.db = self.client[db_name]

        blogs_uri = settings.BLOGS_MONGO_URI or build_mongo_uri_for_database(settings.MONGO_URI, "blogs")
        if blogs_uri and blogs_uri != settings.MONGO_URI:
            self.blogs_client = MongoClient(blogs_uri, serverSelectionTimeoutMS=10000)
            self.blogs_db = self.blogs_client.get_default_database()
            if self.blogs_db is None:
                parsed = urlparse(blogs_uri)
                self.blogs_db = self.blogs_client[parsed.path.lstrip("/") or "blogs"]
        else:
            self.blogs_db = self.db

        self.client.admin.command("ping")
        if self.blogs_client:
            self.blogs_client.admin.command("ping")

    def close(self) -> None:
        if self.client:
            self.client.close()
        if self.blogs_client:
            self.blogs_client.close()


def build_mongo_uri_for_database(mongo_uri: str, database_name: str) -> str:
    if not mongo_uri or not database_name:
        return ""

    parsed = urlparse(mongo_uri)
    next_path = f"/{database_name}"
    return urlunparse(parsed._replace(path=next_path))


mongo = MongoManager()

