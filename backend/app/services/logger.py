"""Structured JSON logging for the AegisAI backend.

Every record is a single JSON line on stdout with at least:
timestamp, level, endpoint, model_version, latency_ms, status_code.

The request-logging middleware emits one record per HTTP request; the
``/predict`` endpoint enriches its record with ``model_version`` (via
``request.state``) and emits an additional prediction record.
"""
import datetime
import json
import logging
import os
import sys
from collections import deque

_CONFIGURED = False

# In-process ring buffer of recent request records for the log-analysis tool.
# Single uvicorn worker (default) => complete view; with multiple workers each
# process sees only its own slice (documented limitation, fine for this scope).
LOG_BUFFER_SIZE = int(os.getenv("LOG_BUFFER_SIZE", "2000"))
log_buffer: deque = deque(maxlen=LOG_BUFFER_SIZE)


def record_log_entry(entry: dict) -> None:
    log_buffer.append(entry)


def clear_log_buffer() -> None:
    log_buffer.clear()


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        payload.setdefault(
            "timestamp", datetime.datetime.now(datetime.timezone.utc).isoformat()
        )
        return json.dumps(payload)


def get_logger(name: str = "aegis") -> logging.Logger:
    global _CONFIGURED
    logger = logging.getLogger(name)
    if not _CONFIGURED:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
        logger.propagate = False
        _CONFIGURED = True
    return logger


def log_request(
    logger: logging.Logger,
    *,
    endpoint: str,
    method: str,
    status_code: int,
    latency_ms: float,
    model_version: str | None = None,
) -> None:
    entry = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "endpoint": endpoint,
        "method": method,
        "model_version": model_version,
        "latency_ms": round(latency_ms, 3),
        "status_code": status_code,
    }
    record_log_entry(entry)
    logger.info("request", extra={"extra_fields": entry})


def log_prediction(
    logger: logging.Logger,
    *,
    model_version: str,
    fraud_probability: float,
    is_fraud: bool,
    latency_ms: float,
) -> None:
    logger.info(
        "prediction",
        extra={
            "extra_fields": {
                "endpoint": "/predict",
                "model_version": model_version,
                "fraud_probability": fraud_probability,
                "is_fraud": is_fraud,
                "latency_ms": round(latency_ms, 3),
            }
        },
    )
