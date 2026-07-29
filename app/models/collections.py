from bson import ObjectId

from app.db.mongo import mongo


def object_id(value: str | ObjectId) -> ObjectId:
    if isinstance(value, ObjectId):
        return value
    return ObjectId(str(value))


def users_collection():
    return mongo.db["users"]


def news_collection():
    return mongo.db["news"]


def comments_collection():
    return mongo.db["comments"]


def visits_collection():
    return mongo.db["visits"]


def alert_subscriptions_collection():
    return mongo.db["alertsubscriptions"]


def push_subscriptions_collection():
    return mongo.db["pushsubscriptions"]


def blog_drafts_collection():
    return mongo.db["blogdrafts"]


def blogs_collection():
    return mongo.blogs_db["blogs"]

