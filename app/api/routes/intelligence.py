from fastapi import APIRouter

from app.api.deps import OptionalUser
from app.core.exceptions import bad_request
from app.services.news import (
    build_intelligence_overview,
    get_event_timeline,
    list_event_clusters,
    run_semantic_search,
)


router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])


@router.get("/overview")
def get_overview():
    return build_intelligence_overview()


@router.get("/events")
def get_events():
    return {"items": list_event_clusters()}


@router.get("/events/{event_id}")
def get_event(event_id: str):
    item = get_event_timeline(event_id)
    if not item:
        raise bad_request("Event not found")
    return {"item": item}


@router.get("/search")
def search_intelligence(q: str, user=OptionalUser):
    query = str(q or "").strip()
    if not query:
        raise bad_request("Search query is required")
    return {
        "items": run_semantic_search(
            query=query,
            user_favorite_links=(user or {}).get("favoriteLinks", []),
            user_liked_links=(user or {}).get("likedLinks", []),
            user_disliked_links=(user or {}).get("dislikedLinks", []),
        )
    }

