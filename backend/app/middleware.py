"""ASGI middleware emitting one structured JSON log record per HTTP request."""
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.services.logger import get_logger, log_request

# High-frequency / low-signal paths excluded from request logs.
SKIP_PATHS = {"/metrics"}

logger = get_logger("aegis")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in SKIP_PATHS:
            return await call_next(request)
        start = time.perf_counter()
        response = await call_next(request)
        latency_ms = (time.perf_counter() - start) * 1000.0
        log_request(
            logger,
            endpoint=request.url.path,
            method=request.method,
            status_code=response.status_code,
            latency_ms=latency_ms,
            model_version=getattr(request.state, "model_version", None),
        )
        return response
