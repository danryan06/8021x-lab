from fastapi import APIRouter
from sqlalchemy import text

from app.config import get_settings
from app.db import SessionLocal
from app.integrations.freeradius.health import freeradius_health_detail
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
    fr_status, fr_detail = freeradius_health_detail()
    components.append(
        HealthComponent(
            name="freeradius",
            status=fr_status,
            detail=fr_detail,
        )
    )
    components.append(
        HealthComponent(
            name="api",
            status="ok",
            detail="control-plane responding",
        )
    )
    components.append(
        HealthComponent(
            name="ca_adapter",
            status="configured",
            detail=f"adapter={settings.ca_adapter}; data_dir={settings.ca_data_dir}",
        )
    )

    ok_statuses = {"ok", "configured"}
    if any(c.status == "error" for c in components):
        overall = "degraded"
    elif all(c.status in ok_statuses for c in components):
        overall = "ok"
    else:
        overall = "degraded"
    return HealthResponse(status=overall, components=components)
