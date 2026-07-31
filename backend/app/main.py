from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, ca, clients, events, health, labs, users
from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title="802.1X Lab API",
    description="Control plane for the 802.1X Lab educational sandbox.",
    version="0.1.0",
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


@app.get("/")
def root() -> dict:
    return {
        "name": "802.1X Lab",
        "version": "0.1.0",
        "docs": "/docs",
        "api": "/api/health",
    }
