from fastapi import APIRouter

from app.core.security import CurrentUser
from app.schemas.alerts import AlertCreatePayload, AlertUpdatePayload
from app.services.alerts import check_alerts, create_alert, delete_alert, list_alerts, toggle_alert


router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("")
@router.get("/")
def get_alerts(user=CurrentUser):
    return {"items": list_alerts(user["_id"])}


@router.post("", status_code=201)
@router.post("/", status_code=201)
def add_alert(payload: AlertCreatePayload, user=CurrentUser):
    return {"item": create_alert(payload.model_dump(), user["_id"])}


@router.patch("/{alert_id}")
def update_alert(alert_id: str, payload: AlertUpdatePayload, user=CurrentUser):
    return {"item": toggle_alert(alert_id, payload.enabled, user["_id"])}


@router.delete("/{alert_id}")
def remove_alert(alert_id: str, user=CurrentUser):
    delete_alert(alert_id, user["_id"])
    return {"ok": True}


@router.get("/check")
def run_alert_check(user=CurrentUser):
    return {"items": check_alerts(user["_id"])}
