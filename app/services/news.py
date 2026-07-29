import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import requests
from pymongo import DESCENDING, UpdateOne

from app.core.config import get_settings
from app.models.collections import blogs_collection, comments_collection, news_collection, users_collection
from app.services.push import notify_users_about_matching_articles
from app.utils.news_intelligence import (
    build_neutral_summary,
    cluster_articles,
    escape_regex,
    infer_fallback_tags,
    normalize_feed_item,
    normalize_title_key,
    sanitize_tags,
    score_semantic_match,
)
from app.utils.serialization import serialize_document


CACHE_TTL_MS = 10 * 60 * 1000
feed_cache = {"data": None, "ts": 0}


def _server_root() -> Path:
    return Path(__file__).resolve().parents[2]


def run_rust_rss_fetcher(rss_url: str) -> dict:
    settings = get_settings()
    manifest_path = _server_root() / "rss-fetcher" / "Cargo.toml"
    if settings.RUST_RSS_FETCHER_BIN:
        command = [settings.RUST_RSS_FETCHER_BIN, rss_url]
    else:
        command = ["cargo", "run", "--quiet", "--manifest-path", str(manifest_path), "--", rss_url]
    result = subprocess.run(
        command,
        cwd=_server_root(),
        capture_output=True,
        text=True,
        check=True,
    )
    payload = result.stdout.strip()
    if not payload:
        raise RuntimeError(result.stderr.strip() or "Rust RSS fetcher returned empty output.")
    return json.loads(payload)


def run_python_rss_fetcher(rss_url: str) -> dict:
    response = requests.get(
        rss_url,
        timeout=10,
        headers={"User-Agent": "Mozilla/5.0 (News Intelligence Feed Reader)"},
    )
    response.raise_for_status()
    parsed = feedparser.parse(response.text)
    return {
        "channel": {
            "title": parsed.feed.get("title"),
            "link": parsed.feed.get("link"),
            "lastBuildDate": parsed.feed.get("updated"),
        },
        "items": [
            {
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "pubDate": entry.get("published", "") or entry.get("updated", ""),
                "description": entry.get("summary", ""),
                "guid": entry.get("id", ""),
            }
            for entry in parsed.entries
        ],
    }


def dedupe_normalized_items(items: list[dict]) -> list[dict]:
    articles_by_fingerprint = {}
    for article in items:
        existing = articles_by_fingerprint.get(article.get("fingerprint"))
        if not existing:
            articles_by_fingerprint[article.get("fingerprint")] = article
            continue
        existing_completeness = len(existing.get("description", "")) + len(existing.get("entities", [])) * 10
        next_completeness = len(article.get("description", "")) + len(article.get("entities", [])) * 10
        preferred = article if next_completeness >= existing_completeness else existing
        secondary = existing if preferred is article else article
        preferred["duplicateLinks"] = list(dict.fromkeys((preferred.get("duplicateLinks") or []) + [secondary.get("link")]))
        articles_by_fingerprint[article.get("fingerprint")] = preferred
    return list(articles_by_fingerprint.values())


def attach_matching_blogs(articles: list[dict]) -> list[dict]:
    if not articles:
        return articles
    article_links = [article.get("link") for article in articles if article.get("link")]
    article_titles = [article.get("title", "").strip() for article in articles if article.get("title")]
    filters = [
        {"url": {"$in": article_links}} if article_links else None,
        {"sourceUrl": {"$in": article_links}} if article_links else None,
        {"title": {"$in": article_titles}} if article_titles else None,
    ]
    filters = [item for item in filters if item]
    if not filters:
        return articles
    blog_candidates = list(
        blogs_collection().find({"$or": filters})
    )
    blog_by_url = {}
    blog_by_source_url = {}
    blog_by_title = {}
    for blog in blog_candidates:
        if blog.get("url"):
            blog_by_url[blog["url"]] = blog
        if blog.get("sourceUrl"):
            blog_by_source_url[blog["sourceUrl"]] = blog
        if blog.get("title"):
            blog_by_title[normalize_title_key(blog["title"])] = blog

    settings = get_settings()
    shaped = []
    for article in articles:
        matched_blog = (
            blog_by_source_url.get(article.get("link"))
            or blog_by_url.get(article.get("link"))
            or blog_by_title.get(normalize_title_key(article.get("title", "")))
        )
        shaped.append(
            {
                **article,
                "blogId": str(matched_blog["_id"]) if matched_blog else None,
                "blogUrl": f"{settings.BLOG_FRONT_END_URI.rstrip('/')}/{matched_blog['_id']}" if matched_blog else "",
            }
        )
    return shaped


def attach_engagement_counts(articles: list[dict]) -> list[dict]:
    if not articles:
        return articles
    article_links = list(dict.fromkeys([article.get("link") for article in articles if article.get("link")]))
    like_counts = users_collection().aggregate(
        [
            {"$match": {"likedLinks": {"$in": article_links}}},
            {"$unwind": "$likedLinks"},
            {"$match": {"likedLinks": {"$in": article_links}}},
            {"$group": {"_id": "$likedLinks", "count": {"$sum": 1}}},
        ]
    )
    dislike_counts = users_collection().aggregate(
        [
            {"$match": {"dislikedLinks": {"$in": article_links}}},
            {"$unwind": "$dislikedLinks"},
            {"$match": {"dislikedLinks": {"$in": article_links}}},
            {"$group": {"_id": "$dislikedLinks", "count": {"$sum": 1}}},
        ]
    )
    comment_counts = comments_collection().aggregate(
        [
            {"$match": {"newsLink": {"$in": article_links}}},
            {"$group": {"_id": "$newsLink", "count": {"$sum": 1}}},
        ]
    )
    like_count_map = {item["_id"]: item["count"] for item in like_counts}
    dislike_count_map = {item["_id"]: item["count"] for item in dislike_counts}
    comment_count_map = {item["_id"]: item["count"] for item in comment_counts}

    return [
        {
            **article,
            "likeCount": like_count_map.get(article.get("link"), 0),
            "dislikeCount": dislike_count_map.get(article.get("link"), 0),
            "commentCount": comment_count_map.get(article.get("link"), 0),
        }
        for article in articles
    ]


def sync_news_from_rss(rss_url: str | None = None) -> dict:
    settings = get_settings()
    rss_url = rss_url or settings.HINDU_HOME_RSS
    if feed_cache["data"] and rss_url == settings.HINDU_HOME_RSS:
        import time

        if int(time.time() * 1000) - feed_cache["ts"] < CACHE_TTL_MS:
            return feed_cache["data"]

    try:
        fetched_feed = run_rust_rss_fetcher(rss_url)
    except Exception:
        fetched_feed = run_python_rss_fetcher(rss_url)

    channel = fetched_feed.get("channel") or {}
    candidate_items = [
        normalize_feed_item(
            item,
            {"sourceName": channel.get("title") or "RSS Feed", "title": channel.get("title") or "RSS Feed"},
        )
        for item in (fetched_feed.get("items") or [])
        if item.get("link")
    ]
    existing_articles = (
        list(
            news_collection().find(
                {
                    "$or": [
                        {"link": {"$in": [item["link"] for item in candidate_items]}},
                        {"fingerprint": {"$in": [item["fingerprint"] for item in candidate_items]}},
                    ]
                },
                {"link": 1, "fingerprint": 1},
            )
        )
        if candidate_items
        else []
    )
    existing_keys = {
        value
        for item in existing_articles
        for value in (item.get("link"), item.get("fingerprint"))
        if value
    }
    normalized_items = dedupe_normalized_items(candidate_items)
    new_articles = [article for article in normalized_items if article.get("link") not in existing_keys and article.get("fingerprint") not in existing_keys]
    if normalized_items:
        operations = [
            UpdateOne(
                {"$or": [{"link": article["link"]}, {"fingerprint": article["fingerprint"]}]},
                {
                    "$set": {
                        **article,
                        "duplicateLinks": article.get("duplicateLinks", []),
                        "updatedAt": datetime.now(timezone.utc),
                    },
                    "$setOnInsert": {
                        "createdAt": datetime.now(timezone.utc),
                    }
                },
                upsert=True,
            )
            for article in normalized_items
        ]
        news_collection().bulk_write(operations, ordered=False)

    payload = {
        "source": channel.get("title") or "RSS Feed",
        "title": channel.get("title"),
        "link": channel.get("link"),
        "updated": channel.get("lastBuildDate"),
        "count": len(normalized_items),
        "items": serialize_document(normalized_items),
    }

    if rss_url == settings.HINDU_HOME_RSS:
        import time

        feed_cache["data"] = payload
        feed_cache["ts"] = int(time.time() * 1000)

    if new_articles:
        notify_users_about_matching_articles(new_articles)
    return payload


def build_news_query(*, tag=None, title=None, date=None, month=None, favorite_links=None) -> dict:
    query = {}
    if isinstance(favorite_links, list):
        query["link"] = {"$in": favorite_links if favorite_links else []}
    normalized_tags = [item.strip().lower() for item in str(tag or "").split(",") if item.strip()]
    if len(normalized_tags) == 1:
        query["tags"] = normalized_tags[0]
    elif len(normalized_tags) > 1:
        query["tags"] = {"$in": normalized_tags}
    if title and title.strip():
        query["title"] = {"$regex": escape_regex(title.strip()), "$options": "i"}
    if date and str(date).strip():
        query["publishedDateKey"] = str(date).strip()
    elif month and str(month).strip():
        query["publishedMonthKey"] = str(month).strip()
    return query


def decorate_article(article: dict, favorite_set: set, liked_set: set, disliked_set: set) -> dict:
    tags = sanitize_tags(article.get("tags") or infer_fallback_tags(article))
    return serialize_document(
        {
            **article,
            "tags": tags,
            "isFavorite": article.get("link") in favorite_set,
            "isLiked": article.get("link") in liked_set,
            "isDisliked": article.get("link") in disliked_set,
        }
    )


def get_paginated_news(
    *,
    tag=None,
    title=None,
    date=None,
    month=None,
    page=None,
    favorite_links=None,
    user_favorite_links=None,
    user_liked_links=None,
    user_disliked_links=None,
) -> dict:
    normalized_page = max(1, int(page or 1))
    limit = 4
    skip = (normalized_page - 1) * limit
    query = build_news_query(tag=tag, title=title, date=date, month=month, favorite_links=favorite_links)
    favorite_set = set(user_favorite_links or [])
    liked_set = set(user_liked_links or [])
    disliked_set = set(user_disliked_links or [])
    news_items = list(
        news_collection().find(query).sort([("publishedAt", DESCENDING), ("createdAt", DESCENDING), ("_id", DESCENDING)]).skip(skip).limit(limit)
    )
    total = news_collection().count_documents(query)
    with_blogs = attach_matching_blogs(news_items)
    with_engagement = attach_engagement_counts(with_blogs)
    return {
        "count": len(news_items),
        "total": total,
        "page": normalized_page,
        "limit": limit,
        "totalPages": max(1, (total + limit - 1) // limit),
        "items": [decorate_article(article, favorite_set, liked_set, disliked_set) for article in with_engagement],
    }


def get_article_by_link(*, link: str, user_favorite_links=None, user_liked_links=None, user_disliked_links=None):
    article = news_collection().find_one({"link": (link or "").strip()})
    if not article:
        return None
    [article_with_blog] = attach_matching_blogs([article])
    [article_with_engagement] = attach_engagement_counts([article_with_blog])
    return decorate_article(
        article_with_engagement,
        set(user_favorite_links or []),
        set(user_liked_links or []),
        set(user_disliked_links or []),
    )


def upsert_article_if_missing(payload: dict):
    link = (payload.get("link") or "").strip()
    if not link:
        return None
    article = news_collection().find_one({"link": link})
    if article:
        return article
    normalized_article = normalize_feed_item(
        {
            "link": link,
            "pubDate": payload.get("pubDate", "") or "",
            "description": payload.get("description", "") or "",
            "title": payload.get("title", "") or "",
        },
        {"sourceName": "User Seeded Article", "title": "User Seeded Article"},
    )
    normalized_article["createdAt"] = datetime.now(timezone.utc)
    normalized_article["updatedAt"] = datetime.now(timezone.utc)
    news_collection().insert_one(normalized_article)
    feed_cache["data"] = None
    feed_cache["ts"] = 0
    return normalized_article


def get_available_tags() -> list[str]:
    stored_tags = news_collection().distinct("tags")
    untagged_articles = list(
        news_collection().find(
            {"$or": [{"tags": {"$exists": False}}, {"tags": {"$size": 0}}]},
            {"title": 1, "description": 1, "link": 1, "category": 1, "subCategory": 1},
        )
    )
    inferred_tags = [tag for article in untagged_articles for tag in infer_fallback_tags(article)]
    return sorted(sanitize_tags(stored_tags + inferred_tags))


def build_intelligence_overview() -> dict:
    articles = list(news_collection().find({}).sort([("publishedAt", DESCENDING), ("createdAt", DESCENDING)]).limit(150))
    clusters = cluster_articles(articles)
    return {
        "eventCount": len(clusters),
        "articleCount": len(articles),
        "breakingCount": len([cluster for cluster in clusters if cluster["articleCount"] >= 2]),
        "topEvents": [
            {
                "id": cluster["id"],
                "title": cluster["title"],
                "summary": cluster["summary"],
                "articleCount": cluster["articleCount"],
                "sourceCount": cluster["sourceCount"],
                "corroborationLabel": cluster["corroborationLabel"],
                "entities": cluster["entities"],
                "coverageShift": cluster["coverageShift"],
                "updatedAt": cluster["updatedAt"],
            }
            for cluster in clusters[:5]
        ],
    }


def list_event_clusters() -> list[dict]:
    articles = list(news_collection().find({}).sort([("publishedAt", DESCENDING), ("createdAt", DESCENDING)]).limit(200))
    return serialize_document(cluster_articles(articles))


def get_event_timeline(event_id: str):
    clusters = list_event_clusters()
    return next((cluster for cluster in clusters if cluster.get("id") == event_id), None)


def run_semantic_search(*, query: str, user_favorite_links=None, user_liked_links=None, user_disliked_links=None) -> list[dict]:
    articles = list(news_collection().find({}).sort([("publishedAt", DESCENDING), ("createdAt", DESCENDING)]).limit(200))
    favorite_set = set(user_favorite_links or [])
    liked_set = set(user_liked_links or [])
    disliked_set = set(user_disliked_links or [])
    matching_articles = []
    for article in articles:
        candidate = {
            **article,
            "semanticScore": score_semantic_match(article, query),
            "summary": build_neutral_summary([article]),
        }
        if candidate["semanticScore"] > 0:
            matching_articles.append(candidate)
    matching_articles.sort(key=lambda item: item["semanticScore"], reverse=True)
    matching_articles = matching_articles[:20]
    with_blogs = attach_matching_blogs(matching_articles)
    with_engagement = attach_engagement_counts(with_blogs)
    return [decorate_article(article, favorite_set, liked_set, disliked_set) for article in with_engagement]


def warm_news_intelligence() -> None:
    sync_news_from_rss()
