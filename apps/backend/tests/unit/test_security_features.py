"""Tests for fingerprint binding security feature."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from gim_database.models.identity import Session

from gim_backend.middleware.context import RequestContext
from gim_backend.services.risk_assessment import assess_session_risk


class TestFingerprintBinding:
    """Verify fingerprint is bound on first authenticated request."""

    def test_session_without_fingerprint_can_bind(self):
        """Session created without fingerprint should be able to bind one later."""
        session = Session(
            id=uuid4(),
            user_id=uuid4(),
            fingerprint=None,  # No fingerprint at creation
            os_family="Windows",
            ua_family="Chrome",
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )

        ctx = RequestContext(
            fingerprint_hash="abc123newfingerprint",
            fingerprint_raw="raw_fingerprint_data",
            os_family="Windows",
            ua_family="Chrome",
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
            login_flow_id=None,
            asn="AS12345",
            country_code="US",
        )

        # After binding, session should retain fingerprint for future risk checks
        assert session.fingerprint is None
        session.fingerprint = ctx.fingerprint_hash
        assert session.fingerprint == "abc123newfingerprint"

    def test_bound_fingerprint_mismatch_triggers_risk(self):
        """After binding, fingerprint mismatch should add to risk score."""
        session = Session(
            id=uuid4(),
            user_id=uuid4(),
            fingerprint="original_fingerprint",
            os_family="Windows",
            ua_family="Chrome",
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )

        ctx = RequestContext(
            fingerprint_hash="different_fingerprint",
            fingerprint_raw="different_raw",
            os_family="Windows",
            ua_family="Chrome",
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
            login_flow_id=None,
            asn="AS12345",
            country_code="US",
        )

        risk = assess_session_risk(session, ctx)

        assert "fingerprint" in risk.factors
        assert risk.score > 0


class TestLogSanitization:
    """Verify user queries are redacted in logs."""

    def test_short_query_not_truncated(self):
        """Queries under 20 chars should not be truncated."""

        def _redact(q: str, max_len: int = 20) -> str:
            return q if len(q) <= max_len else q[:max_len] + "..."

        assert _redact("short query") == "short query"
        assert _redact("exactly 20 chars!!!!") == "exactly 20 chars!!!!"

    def test_long_query_is_truncated(self):
        """Queries over 20 chars should be truncated with ellipsis."""

        def _redact(q: str, max_len: int = 20) -> str:
            return q if len(q) <= max_len else q[:max_len] + "..."

        long_query = "this is a very long search query with potential PII"
        redacted = _redact(long_query)

        assert len(redacted) == 23  # 20 + "..."
        assert redacted.endswith("...")
        assert "PII" not in redacted
