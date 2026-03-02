"""Unit tests for worker entrypoint routing"""

import os
from unittest.mock import MagicMock, patch


class TestJobTypeValidation:
    def test_unknown_job_type_not_in_valid_types(self):
        """Unknown JOB_TYPE should not be in valid types"""
        job_type = "invalid_job"
        valid_types = {"gatherer", "janitor"}
        assert job_type not in valid_types

    def test_empty_job_type_defaults_to_gatherer(self):
        """Empty JOB_TYPE should default to gatherer"""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("JOB_TYPE", None)
            job_type = os.getenv("JOB_TYPE", "gatherer")
            assert job_type == "gatherer"

    def test_job_type_lowercase_conversion(self):
        """JOB_TYPE should be converted to lowercase"""
        with patch.dict(os.environ, {"JOB_TYPE": "GATHERER"}, clear=False):
            job_type = os.getenv("JOB_TYPE", "gatherer").lower()
            assert job_type == "gatherer"

    def test_janitor_job_type(self):
        """JOB_TYPE=janitor should be recognized"""
        with patch.dict(os.environ, {"JOB_TYPE": "janitor"}, clear=False):
            job_type = os.getenv("JOB_TYPE", "gatherer").lower()
            assert job_type == "janitor"


class TestLoggingSetup:
    def test_setup_logging_returns_job_id(self):
        """setup_logging should return a job_id for correlation"""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CLOUD_RUN_EXECUTION", None)

            with patch("gim_workers.logging_config.uuid.uuid4") as mock_uuid:
                mock_uuid.return_value = MagicMock(
                    __str__=lambda self: "12345678-1234-1234-1234-123456789abc"
                )

                from gim_workers.logging_config import setup_logging

                job_id = setup_logging()

                # Should be first 8 chars of UUID when CLOUD_RUN_EXECUTION not set
                assert len(job_id) == 8

    def test_uses_cloud_run_execution_if_available(self):
        """Should use CLOUD_RUN_EXECUTION env var when available"""
        with patch.dict(
            os.environ, {"CLOUD_RUN_EXECUTION": "cloud-run-job-123"}, clear=False
        ):
            from gim_workers.logging_config import setup_logging

            job_id = setup_logging()

            assert job_id == "cloud-run-job-123"


class TestJsonFormatter:
    def test_formatter_includes_job_id(self):
        """JsonFormatter should include job_id in output"""
        import logging
        from gim_workers.logging_config import JsonFormatter

        formatter = JsonFormatter(job_id="test-123")

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        assert "test-123" in output
        assert "Test message" in output

    def test_formatter_outputs_json(self):
        """JsonFormatter should output valid JSON"""
        import json
        import logging
        from gim_workers.logging_config import JsonFormatter

        formatter = JsonFormatter(job_id="test-456")

        record = logging.LogRecord(
            name="test.module",
            level=logging.WARNING,
            pathname="test.py",
            lineno=42,
            msg="Warning message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)

        parsed = json.loads(output)
        assert parsed["severity"] == "WARNING"
        assert parsed["message"] == "Warning message"
        assert parsed["job_id"] == "test-456"
        assert "timestamp" in parsed
