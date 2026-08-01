"""Publish lab CA material into the FreeRADIUS trust store on the shared volume."""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from app.config import get_settings
from app.integrations.ca import get_ca_adapter
from app.integrations.freeradius.sync import request_restart

logger = logging.getLogger(__name__)
settings = get_settings()


def trusted_dir() -> Path:
    path = Path(settings.freeradius_config_dir) / "trusted"
    path.mkdir(parents=True, exist_ok=True)
    return path


def publish_lab_ca(lab_id: UUID, common_name: str = "802.1X Lab Root CA") -> Path:
    """Ensure lab root exists and write/update the FreeRADIUS client-trust CA bundle."""
    adapter = get_ca_adapter()
    info = adapter.ensure_root(lab_id, common_name)
    root_path = Path(info.storage_ref)
    if not root_path.exists():
        raise FileNotFoundError(f"Lab CA cert missing at {root_path}")

    lab_ca_pem = root_path.read_text(encoding="utf-8")
    out_lab = trusted_dir() / f"lab-{lab_id}.pem"
    out_lab.write_text(lab_ca_pem, encoding="utf-8")

    # Bundle all lab CAs (+ optional bootstrap CA copy) for FreeRADIUS ca_file.
    bundle_parts: list[str] = []
    bootstrap = Path(settings.freeradius_ca_path)
    if bootstrap.exists():
        bundle_parts.append(bootstrap.read_text(encoding="utf-8").strip())
    for pem in sorted(trusted_dir().glob("lab-*.pem")):
        bundle_parts.append(pem.read_text(encoding="utf-8").strip())
    bundle_path = trusted_dir() / "ca-bundle.pem"
    bundle_path.write_text("\n".join(p for p in bundle_parts if p) + "\n", encoding="utf-8")

    # Flag for entrypoint / operator visibility; ca_file changes need a full restart.
    (trusted_dir() / "updated.flag").write_text("updated\n", encoding="utf-8")
    request_restart()
    logger.info("Published lab CA for lab_id=%s to %s (restart requested)", lab_id, bundle_path)
    return bundle_path
