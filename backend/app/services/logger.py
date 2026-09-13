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

_CONFIGURED = False


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        payload = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
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
    logger.info(
        "request",
        extra={
            "extra_fields": {
                "endpoint": endpoint,
                "method": method,
                "model_version": model_version,
                "latency_ms": round(latency_ms, 3),
                "status_code": status_code,
            }
        },
    )


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
