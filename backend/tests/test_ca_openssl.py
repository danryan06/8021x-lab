import shutil
import subprocess
from uuid import uuid4

import pytest

from app.integrations.ca.openssl_adapter import OpenSslLocalCaAdapter

pytestmark = pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl not installed")


@pytest.fixture
def adapter() -> OpenSslLocalCaAdapter:
    return OpenSslLocalCaAdapter()


def _crl_text(crl_path) -> str:
    return subprocess.check_output(
        ["openssl", "crl", "-in", str(crl_path), "-noout", "-text"], text=True
    )


def test_ensure_root_creates_ca_database(adapter: OpenSslLocalCaAdapter) -> None:
    lab = uuid4()
    info = adapter.ensure_root(lab, "Test Lab CA")
    assert adapter.root_cert_path(lab).exists()
    assert "Test Lab CA" in info.subject
    lab_dir = adapter.root_cert_path(lab).parent.parent
    assert (lab_dir / "db" / "index.txt").exists()
    assert (lab_dir / "openssl.cnf").exists()


def test_issue_client_cert_chains_to_root(adapter: OpenSslLocalCaAdapter) -> None:
    lab = uuid4()
    issued = adapter.issue_client_cert(lab, "alice", days=90)
    assert issued.serial
    assert "alice" in issued.subject
    assert adapter.client_cert_path(lab, "alice").exists()
    assert adapter.client_p12_path(lab, "alice").exists()
    verify = subprocess.run(
        [
            "openssl",
            "verify",
            "-CAfile",
            str(adapter.root_cert_path(lab)),
            str(adapter.client_cert_path(lab, "alice")),
        ],
        capture_output=True,
        text=True,
    )
    assert verify.returncode == 0, verify.stderr


def test_reissue_same_identity_gets_new_serial(adapter: OpenSslLocalCaAdapter) -> None:
    lab = uuid4()
    first = adapter.issue_client_cert(lab, "bob")
    second = adapter.issue_client_cert(lab, "bob")
    assert first.serial != second.serial


def test_revoke_puts_serial_on_crl(adapter: OpenSslLocalCaAdapter) -> None:
    lab = uuid4()
    keep = adapter.issue_client_cert(lab, "keep")
    revoke_me = adapter.issue_client_cert(lab, "revokeme")
    adapter.revoke(lab, revoke_me.storage_ref)

    crl = adapter.crl_path(lab)
    assert crl.exists()
    text = _crl_text(crl)
    # openssl prints serials uppercase without a leading 0x.
    assert revoke_me.serial.lstrip("0").upper() in text.upper()
    assert keep.serial.lstrip("0").upper() not in text.upper() or keep.serial == revoke_me.serial


def test_generate_crl_without_revocations(adapter: OpenSslLocalCaAdapter) -> None:
    lab = uuid4()
    adapter.ensure_root(lab)
    crl = adapter.generate_crl(lab)
    assert crl.exists()
    assert "X509 CRL" in _crl_text(crl) or "Certificate Revocation List" in _crl_text(crl)


def test_revoke_missing_cert_raises(adapter: OpenSslLocalCaAdapter) -> None:
    lab = uuid4()
    adapter.ensure_root(lab)
    with pytest.raises(FileNotFoundError):
        adapter.revoke(lab, "/nonexistent/cert.crt")
