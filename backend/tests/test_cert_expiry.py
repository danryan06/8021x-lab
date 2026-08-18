from datetime import UTC, datetime, timedelta

from app.models.entities import CertStatus
from app.services.certificates import effective_cert_status


class TestEffectiveCertStatus:
    def test_active_in_the_future_stays_active(self) -> None:
        later = datetime.now(UTC) + timedelta(days=30)
        assert effective_cert_status(CertStatus.active, later) == CertStatus.active

    def test_active_in_the_past_reads_expired(self) -> None:
        earlier = datetime.now(UTC) - timedelta(days=1)
        assert effective_cert_status(CertStatus.active, earlier) == CertStatus.expired

    def test_naive_not_after_is_treated_as_utc(self) -> None:
        earlier = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
        assert effective_cert_status(CertStatus.active, earlier) == CertStatus.expired

    def test_revoked_is_not_overwritten(self) -> None:
        earlier = datetime.now(UTC) - timedelta(days=1)
        assert effective_cert_status(CertStatus.revoked, earlier) == CertStatus.revoked

    def test_missing_not_after_stays_as_stored(self) -> None:
        assert effective_cert_status(CertStatus.active, None) == CertStatus.active
        assert effective_cert_status(CertStatus.pending, None) == CertStatus.pending
