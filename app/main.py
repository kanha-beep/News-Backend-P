from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes import alerts, analytics, auth, blog_drafts, comments, intelligence, legacy, news, push, uploads
from app.core.config import get_settings
from app.core.exceptions import AppError, app_error_handler, generic_error_handler
from app.core.middleware import BodySizeLimitMiddleware, CSRFMiddleware, RateLimitMiddleware, SecurityHeadersMiddleware
from app.db.mongo import mongo
from app.services.news import sync_news_from_rss, warm_news_intelligence


scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    mongo.connect()
    warm_news_intelligence()
    try:
        if not scheduler.running:
            scheduler.add_job(sync_news_from_rss, CronTrigger.from_crontab(settings.NEWS_SYNC_CRON), replace_existing=True, id="news-sync")
            scheduler.start()
        yield
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)
        mongo.close()


app = FastAPI(lifespan=lifespan)
settings = get_settings()

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(BodySizeLimitMiddleware, max_body_size=settings.MAX_REQUEST_SIZE_BYTES)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(CSRFMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    session_cookie=settings.SESSION_COOKIE_NAME,
    max_age=settings.COOKIE_MAX_AGE_SECONDS,
    same_site="lax",
    https_only=settings.is_production,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins or ["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(Exception, generic_error_handler)


@app.get("/api/health")
def health():
    return {"ok": True}


app.include_router(auth.router)
app.include_router(news.router)
app.include_router(comments.router)
app.include_router(analytics.router)
app.include_router(alerts.router)
app.include_router(intelligence.router)
app.include_router(blog_drafts.router)
app.include_router(push.router)
app.include_router(uploads.router)
app.include_router(legacy.router)

uploads_dir = Path(__file__).resolve().parents[1] / settings.UPLOAD_DIR
uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")


@app.exception_handler(404)
async def not_found_handler(_request, _exc):
    return JSONResponse(status_code=404, content={"error": "Route not found"})
