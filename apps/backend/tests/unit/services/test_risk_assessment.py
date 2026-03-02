"""
Risk Assessment Service Tests

Tests the risk scoring logic for soft metadata binding.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_session():
    """Session with baseline metadata."""
    session = MagicMock()
    session.fingerprint = "a" * 64
    session.os_family = "Mac OS X"
    session.ua_family = "Chrome"
    session.asn = "AS15169"
    session.country_code = "US"
    session.deviation_logged_at = None
    return session


@pytest.fixture
def mock_ctx():
    """RequestContext with matching metadata."""
    ctx = MagicMock()
    ctx.fingerprint_hash = "a" * 64
    ctx.os_family = "Mac OS X"
    ctx.ua_family = "Chrome"
    ctx.asn = "AS15169"
    ctx.country_code = "US"
    return ctx


class TestRiskScoring:
    """Tests for assess_session_risk scoring logic."""

    def test_matching_metadata_returns_zero_score(self, mock_session, mock_ctx):
        """All matching = 0.0 risk score."""
        from gim_backend.services.risk_assessment import assess_session_risk

        result = assess_session_risk(mock_session, mock_ctx)

        assert result.score == 0.0
        assert result.should_reauthenticate is False
        assert result.should_log is False
        assert len(result.factors) == 0

    def test_country_change_triggers_reauthentication(self, mock_session, mock_ctx):
        """Country mismatch = 0.8; exceeds 0.7 threshold."""
        from gim_backend.services.risk_assessment import assess_session_risk

        mock_ctx.country_code = "RU"

        result = assess_session_risk(mock_session, mock_ctx)

        assert result.score == 0.8
        assert result.should_reauthenticate is True
        assert "country:US->RU" in result.factors

    def test_os_and_ua_mismatch_medium_risk(self, mock_session, mock_ctx):
        """OS + UA mismatch = 0.3 + 0.2 = 0.5; medium risk."""
        from gim_backend.services.risk_assessment import assess_session_risk

        mock_ctx.os_family = "Windows"
        mock_ctx.ua_family = "Firefox"

        result = assess_session_risk(mock_session, mock_ctx)

        assert result.score == 0.5
        assert result.should_reauthenticate is False
        assert result.should_log is True
        assert len(result.factors) == 2

    def test_asn_change_only_low_risk(self, mock_session, mock_ctx):
        """ASN change alone = 0.2; below 0.3 threshold."""
        from gim_backend.services.risk_assessment import assess_session_risk

        mock_ctx.asn = "AS7922"

        result = assess_session_risk(mock_session, mock_ctx)

        assert result.score == 0.2
        assert result.should_reauthenticate is False
        assert result.should_log is False

    def test_all_mismatches_cumulative(self, mock_session, mock_ctx):
        """All mismatches = 0.1 + 0.3 + 0.2 + 0.2 + 0.8 = 1.6"""
        from gim_backend.services.risk_assessment import assess_session_risk

        mock_ctx.fingerprint_hash = "b" * 64
        mock_ctx.os_family = "Windows"
        mock_ctx.ua_family = "Firefox"
        mock_ctx.asn = "AS7922"
        mock_ctx.country_code = "CN"

        result = assess_session_risk(mock_session, mock_ctx)

        assert result.score == 1.6
        assert result.should_reauthenticate is True
        assert len(result.factors) == 5


class TestLogThrottling:
    """Tests for deviation log throttling."""

    def test_first_deviation_should_log(self, mock_session, mock_ctx):
        """No previous log = should log."""
        from gim_backend.services.risk_assessment import assess_session_risk

        mock_ctx.os_family = "Windows"
        mock_session.deviation_logged_at = None

        result = assess_session_risk(mock_session, mock_ctx)

        assert result.should_log is True

    def test_recent_deviation_throttled(self, mock_session, mock_ctx):
        """Logged 1 hour ago = should NOT log."""
        from gim_backend.services.risk_assessment import assess_session_risk

        mock_ctx.os_family = "Windows"
        mock_session.deviation_logged_at = datetime.now(UTC) - timedelta(hours=1)

        result = assess_session_risk(mock_session, mock_ctx)

        assert result.should_log is False

    def test_old_deviation_logs_again(self, mock_session, mock_ctx):
        """Logged 5 hours ago = should log again."""
        from gim_backend.services.risk_assessment import assess_session_risk

        mock_ctx.os_family = "Windows"
        mock_session.deviation_logged_at = datetime.now(UTC) - timedelta(hours=5)

        result = assess_session_risk(mock_session, mock_ctx)

        assert result.should_log is True


class TestNullSafety:
    """Tests for null/missing metadata handling."""

    def test_null_session_metadata_no_mismatch(self, mock_session, mock_ctx):
        """None in session = not a mismatch."""
        from gim_backend.services.risk_assessment import assess_session_risk

        mock_session.os_family = None
        mock_session.country_code = None

        result = assess_session_risk(mock_session, mock_ctx)

        assert result.score == 0.0

    def test_null_context_metadata_no_mismatch(self, mock_session, mock_ctx):
        """None in context = not a mismatch."""
        from gim_backend.services.risk_assessment import assess_session_risk

        mock_ctx.os_family = None
        mock_ctx.country_code = None

        result = assess_session_risk(mock_session, mock_ctx)

        assert result.score == 0.0

    def test_case_insensitive_comparison(self, mock_session, mock_ctx):
        """Comparison should be case-insensitive."""
        from gim_backend.services.risk_assessment import assess_session_risk

        mock_session.os_family = "mac os x"
        mock_ctx.os_family = "Mac OS X"

        result = assess_session_risk(mock_session, mock_ctx)

        assert result.score == 0.0
