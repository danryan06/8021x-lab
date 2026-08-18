"""Bring an empty (or outdated) database up to the current schema.

A fresh Postgres volume has no tables. Operators should not run Alembic: the
backend container does this on every start, then seeds the Default Lab if it
is missing. Re-running is a no-op once the schema is current.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RETRIES = 30
DEFAULT_DELAY_SECONDS = 2.0


def apply_schema() -> None:
    """Run `alembic upgrade head` against this backend tree."""
    from alembic.config import Config

    from alembic import command

    ini = BACKEND_ROOT / "alembic.ini"
    cfg = Config(str(ini))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    command.upgrade(cfg, "head")


def prepare_database(
    *,
    retries: int = DEFAULT_RETRIES,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
) -> None:
    """Retry schema apply until Postgres accepts connections (or give up)."""
    last: BaseException | None = None
    attempts = max(1, retries)
    for attempt in range(1, attempts + 1):
        try:
            apply_schema()
            if attempt > 1:
                logger.info("Database schema applied on attempt %s", attempt)
            else:
                logger.info("Database schema is at head")
            return
        except Exception as exc:
            last = exc
            logger.warning(
                "Database not ready for migrations (attempt %s/%s): %s",
                attempt,
                attempts,
                exc,
            )
            if attempt < attempts:
                time.sleep(delay_seconds)
    raise RuntimeError(
        f"alembic upgrade head failed after {attempts} attempts"
    ) from last


def seed_default_lab() -> None:
    from app.seed import main as seed_main

    seed_main()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if os.environ.get("SKIP_SCHEMA_SETUP", "").strip() in {"1", "true", "yes"}:
        logger.info("SKIP_SCHEMA_SETUP is set; not applying schema")
        return
    prepare_database()
    seed_default_lab()


if __name__ == "__main__":
    main()
