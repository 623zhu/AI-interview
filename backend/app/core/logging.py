"""Structured JSON logging configuration."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.observability import get_request_id


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id(),
        }

        for key in (
            "event",
            "method",
            "path",
            "status_code",
            "duration_ms",
            "total_ms",
            "client_ip",
            "error_code",
            "trace_id",
            "session_id",
            "turn",
            "user_msg_id",
            "timings",
            "counters",
            "metadata",
            "retry_count",
            "ended",
            "tool_name",
            "result_count",
            "rag_k",
            "rerank_enabled",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    formatter = JsonLogFormatter()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    log_dir = Path(settings.LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)

    app_file_handler = RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=settings.LOG_FILE_MAX_BYTES,
        backupCount=settings.LOG_FILE_BACKUP_COUNT,
        encoding="utf-8",
    )
    app_file_handler.setFormatter(formatter)

    timing_file_handler = RotatingFileHandler(
        log_dir / "interview_timing.log",
        maxBytes=settings.LOG_FILE_MAX_BYTES,
        backupCount=settings.LOG_FILE_BACKUP_COUNT,
        encoding="utf-8",
    )
    timing_file_handler.setFormatter(formatter)
    timing_file_handler.addFilter(lambda record: getattr(record, "event", None) == "interview_turn_timing")

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.addHandler(app_file_handler)
    root_logger.addHandler(timing_file_handler)
    root_logger.setLevel(level.upper())

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True
