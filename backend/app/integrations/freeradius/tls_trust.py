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


def publish_lab_ca(lab_id: UUID, common_name: str = "802.1X Lab Root CA") -> bool:
    """Ensure lab root exists and write/update the FreeRADIUS client-trust CA bundle.

    Returns True when the bundle changed and a FreeRADIUS restart was requested,
    False when the published trust material was already current.
    """
    adapter = get_ca_adapter()
    info = adapter.ensure_root(lab_id, common_name)
    root_path = Path(info.storage_ref)
    if not root_path.exists():
        raise FileNotFoundError(f"Lab CA cert missing at {root_path}")

    lab_ca_pem = root_path.read_text(encoding="utf-8")
    intermediate = getattr(adapter, "intermediate_cert_path", None)
    if callable(intermediate):
        inter_path = Path(str(intermediate(lab_id)))
        if inter_path.exists():
            lab_ca_pem = inter_path.read_text(encoding="utf-8") + lab_ca_pem
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
    new_bundle = "\n".join(p for p in bundle_parts if p) + "\n"

    # Only bounce FreeRADIUS when the trust bundle actually changed — a restart
    # is a several-second auth outage, and sync is called repeatedly as a no-op.
    unchanged = bundle_path.exists() and bundle_path.read_text(encoding="utf-8") == new_bundle
    if unchanged:
        logger.info("Lab CA for lab_id=%s already published to %s (no restart)", lab_id, bundle_path)
        return False

    bundle_path.write_text(new_bundle, encoding="utf-8")
    # Flag for entrypoint / operator visibility; ca_file changes need a full restart.
    (trusted_dir() / "updated.flag").write_text("updated\n", encoding="utf-8")
    request_restart()
    logger.info("Published lab CA for lab_id=%s to %s (restart requested)", lab_id, bundle_path)
    return True


def publish_lab_crl(lab_id: UUID) -> bool:
    """(Re)generate the lab CRL and refresh the published CRL bundle.

    Returns True when the CRL bundle changed and a FreeRADIUS restart was
    requested. The CRL is always published; whether FreeRADIUS enforces it is
    controlled by FREERADIUS_ENFORCE_CRL in the freeradius container.
    """
    adapter = get_ca_adapter()
    generate_crl = getattr(adapter, "generate_crl", None)
    if generate_crl is None:
        raise NotImplementedError("Active CA adapter does not support CRL generation")
    crl_src = Path(str(generate_crl(lab_id)))
    if not crl_src.exists():
        raise FileNotFoundError(f"Lab CRL missing at {crl_src}")

    out_crl = trusted_dir() / f"crl-lab-{lab_id}.pem"
    out_crl.write_text(crl_src.read_text(encoding="utf-8"), encoding="utf-8")

    bundle_parts = [
        pem.read_text(encoding="utf-8").strip() for pem in sorted(trusted_dir().glob("crl-lab-*.pem"))
    ]
    bundle_path = trusted_dir() / "crl-bundle.pem"
    new_bundle = "\n".join(p for p in bundle_parts if p) + "\n"
    if bundle_path.exists() and bundle_path.read_text(encoding="utf-8") == new_bundle:
        logger.info("Lab CRL for lab_id=%s already current at %s (no restart)", lab_id, bundle_path)
        return False

    bundle_path.write_text(new_bundle, encoding="utf-8")
    (trusted_dir() / "updated.flag").write_text("updated\n", encoding="utf-8")
    request_restart()
    logger.info("Published lab CRL for lab_id=%s to %s (restart requested)", lab_id, bundle_path)
    return True
