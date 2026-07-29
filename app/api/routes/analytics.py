from fastapi import APIRouter, Request

from app.schemas.analytics import VisitPayload
from app.services.analytics import record_visit


router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.post("/visit", status_code=201)
def create_visit(payload: VisitPayload, request: Request):
    record_visit(
        payload=payload.model_dump(),
        headers=dict(request.headers),
        fallback_ip=request.client.host if request.client else "",
    )
    return {"ok": True}

