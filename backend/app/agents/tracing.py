"""Lightweight per-step tracer for the investigation agent.

Each graph node records a span: step name, start time, duration, tokens
in/out, estimated USD cost, and status. Spans travel in graph state, then
fan out to Postgres (agent_traces), Prometheus metrics, and the trace API.
"""
import datetime
import time

# Price per 1M tokens (input, output). Local/stub/unknown models cost nothing.
MODEL_PRICES_PER_M: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (5.00, 15.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "llama3.1:8b": (0.0, 0.0),
    "stub": (0.0, 0.0),
}

TRACED_STEPS = (
    "investigate",
    "get_metrics",
    "analyze_logs",
    "analyze_model",
    "search_knowledge",
    "reason",
    "generate_report",
)


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    price_in, price_out = MODEL_PRICES_PER_M.get(model or "", (0.0, 0.0))
    return round(tokens_in / 1_000_000 * price_in
                 + tokens_out / 1_000_000 * price_out, 6)


def make_span(step: str, started_at: str, duration_ms: float,
              tokens_in: int = 0, tokens_out: int = 0,
              model: str = "", status: str = "ok",
              error: str | None = None) -> dict:
    tokens_in = int(tokens_in or 0)
    tokens_out = int(tokens_out or 0)
    return {
        "step": step,
        "started_at": started_at,
        "duration_ms": round(float(duration_ms), 3),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "tokens": tokens_in + tokens_out,
        "cost_usd": estimate_cost(model, tokens_in, tokens_out),
        "model": model,
        "status": status,
        "error": error,
    }


class Timer:
    """Simple perf timer; use time.perf_counter() diffs with make_span."""

    def __init__(self) -> None:
        self.started_at = now_iso()
        self._t0 = time.perf_counter()

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self._t0) * 1000.0
