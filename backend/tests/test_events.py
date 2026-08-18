from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from app.api.events import to_event_read
from app.models.entities import AuthMethod, AuthResult


def _event(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "id": uuid4(),
        "lab_id": uuid4(),
        "timestamp": datetime.now(UTC),
        "identity": "bob",
        "method": AuthMethod.peap,
        "result": AuthResult.failure,
        "failure_reason": "mschap: MS-CHAP2-Response is incorrect",
        "returned_attributes": {},
        "nas_ip": "10.0.0.10",
        "raw_ref": "DOT1X|1754226000|bob|10.0.0.10|PEAP|Access-Reject|mschap: FAILED",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_to_event_read_includes_raw_ref_and_failure_explanation() -> None:
    event = _event()
    read = to_event_read(event)
    assert read.raw_ref == event.raw_ref
    assert read.lab_id == event.lab_id
    assert read.failure_summary
    assert "MSCHAPv2" in read.failure_summary
    assert read.failure_hint


def test_to_event_read_success_has_no_failure_explanation() -> None:
    event = _event(
        result=AuthResult.success,
        failure_reason=None,
        returned_attributes={"Filter-Id": "corp"},
        raw_ref="DOT1X|1754226000|alice|10.0.0.10|PEAP|Access-Accept|",
    )
    read = to_event_read(event)
    assert read.failure_summary is None
    assert read.failure_hint is None
    assert read.returned_attributes == {"Filter-Id": "corp"}
    assert read.raw_ref == event.raw_ref
