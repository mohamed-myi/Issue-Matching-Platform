"""Structured JSON logging for Cloud Run observability"""

import logging
import logging.config
import os
import uuid
from datetime import datetime, timezone


def setup_logging() -> str:
    """
    Configures JSON structured logging for Cloud Run.
    Returns a unique job_id for correlation across log entries.
    """
    job_id = os.getenv("CLOUD_RUN_EXECUTION", str(uuid.uuid4())[:8])

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": "gim_workers.logging_config.JsonFormatter",
                "job_id": job_id,
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "json",
                "stream": "ext://sys.stdout",
            },
        },
        "root": {
            "level": os.getenv("LOG_LEVEL", "INFO"),
            "handlers": ["console"],
        },
        "loggers": {
            "httpx": {"level": "WARNING"},
            "httpcore": {"level": "WARNING"},
            "sentence_transformers": {"level": "WARNING"},
        },
    }

    logging.config.dictConfig(config)
    return job_id


class JsonFormatter(logging.Formatter):
    """
    Outputs log records as JSON for Cloud Logging ingestion.
    Includes job_id, timestamp, severity, and message.
    """

    def __init__(self, job_id: str = "", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.job_id = job_id

    def format(self, record: logging.LogRecord) -> str:
        import json

        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "severity": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "job_id": self.job_id,
        }

        if hasattr(record, "extra") and record.extra:
            log_entry.update(record.extra)

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)
