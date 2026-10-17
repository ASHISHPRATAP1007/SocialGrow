"""SocialGrow AI — FastAPI backend. Run locally: uvicorn app.main:app --reload"""
import asyncio
import hmac
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .core.lib import ApiError
from .database import init_db
from .routers import admin, ai, analytics, auth, billing, entities, integrations, seed, workspace
from .workers.scheduler import run_task, scheduler_loop

logging.basicConfig(level=logging.INFO)
# httpx logs full URLs — those carry access tokens / app secrets, so keep them out of the logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    task = asyncio.create_task(scheduler_loop()) if settings.ENABLE_SCHEDULER else None
    yield
    if task:
        task.cancel()


app = FastAPI(title="SocialGrow AI API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API = "/api/v1"
for r in (auth, workspace, entities, seed, analytics, ai, integrations, billing, admin):
    app.include_router(r.router, prefix=API)


@app.get("/")
def root():
    return {"name": settings.APP_NAME, "status": "ok", "docs": "/docs"}


@app.get(f"{API}/health")
def health():
    return {"status": "ok"}


@app.post(f"{API}/cron/run")
def cron_run(task: str = "daily", x_cron_secret: str | None = Header(default=None)):
    """For free external cron services (e.g. cron-job.org): task=sync every 6h, task=daily once a day."""
    if not settings.CRON_SECRET or not x_cron_secret or not hmac.compare_digest(x_cron_secret, settings.CRON_SECRET):
        raise ApiError("Unauthorized", 401)
    if task not in ("sync", "daily"):
        raise ApiError("task must be sync or daily")
    return {"result": run_task(task)}
