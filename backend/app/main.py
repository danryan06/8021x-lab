import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, auth_tests, ca, clients, events, freeradius, health, labs, radius_target, users
from app.config import get_settings
from app.db import SessionLocal
from app.integrations.freeradius.sql_sync import sync_all_users
from app.integrations.freeradius.sync import bootstrap_radius_runtime
from app.workers.auth_log_ingestion import run_ingestion_task

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Best-effort bootstrap: migrations may still be running on first boot.
    try:
        with SessionLocal() as db:
            sync_all_users(db)
            bootstrap_radius_runtime(db)
        logger.info("FreeRADIUS control-plane sync bootstrap complete")
    except Exception:
        logger.exception("FreeRADIUS bootstrap sync deferred (DB/schema may not be ready yet)")

    stop_event = asyncio.Event()
    ingestion_task = asyncio.create_task(run_ingestion_task(stop_event))
    try:
        yield
    finally:
        stop_event.set()
        ingestion_task.cancel()
        try:
            await ingestion_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="802.1X Lab API",
    description="Control plane for the 802.1X Lab educational sandbox.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(labs.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(clients.router, prefix="/api")
app.include_router(events.router, prefix="/api")
app.include_router(ca.router, prefix="/api")
app.include_router(auth_tests.router, prefix="/api")
app.include_router(freeradius.router, prefix="/api")
app.include_router(radius_target.router, prefix="/api")


@app.get("/")
def root() -> dict:
    return {
        "name": "802.1X Lab",
        "version": "0.1.0",
        "docs": "/docs",
        "api": "/api/health",
    }
