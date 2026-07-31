from fastapi import APIRouter
from sqlalchemy import text

from app.config import get_settings
from app.db import SessionLocal
from app.schemas.entities import HealthComponent, HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    components: list[HealthComponent] = []

    # Database — keep the probe fast so /api/health stays usable under load.
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        components.append(HealthComponent(name="database", status="ok"))
    except Exception as exc:
        # Collapse multi-line driver traces into a single detail string for the UI.
        detail = " ".join(str(exc).split())
        components.append(HealthComponent(name="database", status="error", detail=detail[:500]))

    settings = get_settings()
    components.append(
        HealthComponent(
            name="freeradius_integration",
            status="configured",
            detail=f"config_dir={settings.freeradius_config_dir}",
        )
    )
    components.append(
        HealthComponent(
            name="ca_adapter",
            status="configured",
            detail=f"adapter={settings.ca_adapter}",
        )
    )

    overall = "ok" if all(c.status in {"ok", "configured"} for c in components) else "degraded"
    return HealthResponse(status=overall, components=components)
