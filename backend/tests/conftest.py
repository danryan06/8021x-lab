"""Point path-like settings at a temp dir before any app module is imported.

app modules freeze `settings = get_settings()` at import time, so these
environment variables must be set before the first `import app.*` in any test.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="dot1x-tests-"))
_REPO_ROOT = Path(__file__).resolve().parents[2]

os.environ.setdefault("FREERADIUS_CONFIG_DIR", str(_TMP / "freeradius"))
os.environ.setdefault("FREERADIUS_AUTH_LOG_PATH", str(_TMP / "freeradius" / "logs" / "auth.log"))
os.environ.setdefault("FREERADIUS_CA_PATH", str(_TMP / "freeradius" / "certs" / "ca.pem"))
os.environ.setdefault("CA_DATA_DIR", str(_TMP / "ca"))
os.environ.setdefault("RADIUS_HOST_IP_FILE", str(_TMP / "freeradius" / "host-ip"))
# Use the real repo template so rendering is tested against what ships.
os.environ.setdefault(
    "FREERADIUS_TEMPLATES_DIR", str(_REPO_ROOT / "services" / "freeradius" / "templates")
)
