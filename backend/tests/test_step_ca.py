from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from app.integrations.ca import step_ca as step_ca_mod
from app.integrations.ca.step_ca import StepCaAdapter


def test_ensure_root_requires_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(step_ca_mod.settings, "step_ca_url", "")
    adapter = StepCaAdapter()
    with pytest.raises(NotImplementedError, match="STEP_CA_URL"):
        adapter.ensure_root(uuid4())


def test_ensure_root_writes_pem_from_http(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(step_ca_mod.settings, "ca_data_dir", str(tmp_path))
    monkeypatch.setattr(step_ca_mod.settings, "step_ca_url", "https://step-ca.example")
    pem = "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/root"
        return httpx.Response(200, text=pem)

    transport = httpx.MockTransport(handler)
    adapter = StepCaAdapter()
    adapter._client = lambda: httpx.Client(  # type: ignore[method-assign]
        transport=transport, base_url="https://step-ca.example"
    )
    lab = uuid4()
    info = adapter.ensure_root(lab)
    assert adapter.root_cert_path(lab).read_text(encoding="utf-8") == pem
    assert info.storage_ref.endswith("root.crt")


def test_issue_requires_token(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(step_ca_mod.settings, "ca_data_dir", str(tmp_path))
    monkeypatch.setattr(step_ca_mod.settings, "step_ca_url", "https://step-ca.example")
    monkeypatch.setattr(step_ca_mod.settings, "step_ca_token", "")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n")

    adapter = StepCaAdapter()
    adapter._client = lambda: httpx.Client(  # type: ignore[method-assign]
        transport=httpx.MockTransport(handler), base_url="https://step-ca.example"
    )
    with pytest.raises(NotImplementedError, match="STEP_CA_TOKEN"):
        adapter.issue_client_cert(uuid4(), "alice")


def test_ensure_intermediate_is_not_a_lab_operation(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(step_ca_mod.settings, "ca_data_dir", str(tmp_path))
    monkeypatch.setattr(step_ca_mod.settings, "step_ca_url", "https://step-ca.example")
    pem = "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=pem)

    adapter = StepCaAdapter()
    adapter._client = lambda: httpx.Client(  # type: ignore[method-assign]
        transport=httpx.MockTransport(handler), base_url="https://step-ca.example"
    )
    with pytest.raises(NotImplementedError, match="own issuer"):
        adapter.ensure_intermediate(uuid4())


def test_issue_writes_cert_from_sign_response(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(step_ca_mod.settings, "ca_data_dir", str(tmp_path))
    monkeypatch.setattr(step_ca_mod.settings, "step_ca_url", "https://step-ca.example")
    monkeypatch.setattr(step_ca_mod.settings, "step_ca_token", "ott-1")
    root_pem = "-----BEGIN CERTIFICATE-----\nMIIBroot\n-----END CERTIFICATE-----\n"
    client_pem = "-----BEGIN CERTIFICATE-----\nMIIBclient\n-----END CERTIFICATE-----\n"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/root":
            return httpx.Response(200, text=root_pem)
        assert request.url.path == "/1.0/sign"
        body = request.read()
        assert b"ott-1" in body
        return httpx.Response(200, json={"crt": client_pem, "ca": root_pem})

    adapter = StepCaAdapter()
    adapter._client = lambda: httpx.Client(  # type: ignore[method-assign]
        transport=httpx.MockTransport(handler), base_url="https://step-ca.example"
    )

    def fake_openssl(args: list[str]) -> None:
        if args[0] == "req":
            Path(args[args.index("-keyout") + 1]).write_text("key", encoding="utf-8")
            Path(args[args.index("-out") + 1]).write_text(
                "-----BEGIN CERTIFICATE REQUEST-----\nMIIB\n-----END CERTIFICATE REQUEST-----\n",
                encoding="utf-8",
            )
            return
        if args[0] == "pkcs12":
            Path(args[args.index("-out") + 1]).write_bytes(b"p12")
            return
        raise AssertionError(args)

    monkeypatch.setattr(step_ca_mod, "_run_openssl", fake_openssl)
    monkeypatch.setattr(step_ca_mod, "_serial_from_pem", lambda _pem: "01")
    lab = uuid4()
    issued = adapter.issue_client_cert(lab, "alice", days=30)
    assert issued.serial == "01"
    assert adapter.client_cert_path(lab, "alice").read_text(encoding="utf-8") == client_pem
    assert adapter.client_p12_path(lab, "alice").read_bytes() == b"p12"
