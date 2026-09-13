"""Tool: analyze_logs — anomaly detection over the structured request log buffer.

Detects error spikes (5xx rate), latency spikes (recent p95 vs baseline),
and reports per-endpoint volume plus the model mix. Pure function over the
in-process ring buffer (see app.services.logger), so it is deterministic
and unit-testable.
"""
import datetime
import re

from app.services.logger import log_buffer

TIME_RANGE_RE = re.compile(r"^\s*(\d+)\s*([mhd])\s*$", re.IGNORECASE)


def parse_time_range(time_range: str | None) -> datetime.timedelta | None:
    if not time_range:
        return None
    match = TIME_RANGE_RE.match(time_range)
    if not match:
        raise ValueError(f"Invalid time_range {time_range!r}; use like '15m', '2h', '1d'.")
    amount, unit = int(match.group(1)), match.group(2).lower()
    return {"m": datetime.timedelta(minutes=amount),
            "h": datetime.timedelta(hours=amount),
            "d": datetime.timedelta(days=amount)}[unit]


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(int(pct / 100 * len(ordered)), len(ordered) - 1)
    return ordered[index]


def analyze_logs(time_range: str | None = None) -> dict:
    """Analyze buffered request logs inside the window (or all if None)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    window = parse_time_range(time_range)
    entries = list(log_buffer)
    if window is not None:
        cutoff = now - window
        entries = [e for e in entries
                   if datetime.datetime.fromisoformat(e["timestamp"]) >= cutoff]

    total = len(entries)
    errors = [e for e in entries if 500 <= int(e.get("status_code", 0)) < 600]
    latencies = [float(e.get("latency_ms", 0.0)) for e in entries]
    by_endpoint: dict[str, int] = {}
    model_mix: dict[str, int] = {}
    for entry in entries:
        by_endpoint[entry.get("endpoint", "?")] = by_endpoint.get(entry.get("endpoint", "?"), 0) + 1
        version = entry.get("model_version") or "n/a"
        model_mix[version] = model_mix.get(version, 0) + 1

    error_rate = len(errors) / total if total else 0.0
    p50 = _percentile(latencies, 50)
    p95 = _percentile(latencies, 95)

    findings: list[str] = []
    # Spike detection: second half of the window vs first half.
    ordered = sorted(entries, key=lambda e: e["timestamp"])
    half = len(ordered) // 2
    if half >= 5:
        first, second = ordered[:half], ordered[half:]
        first_err = sum(1 for e in first if 500 <= int(e.get("status_code", 0)) < 600) / len(first)
        second_err = sum(1 for e in second if 500 <= int(e.get("status_code", 0)) < 600) / len(second)
        first_p95 = _percentile([float(e.get("latency_ms", 0.0)) for e in first], 95) or 0.0
        second_p95 = _percentile([float(e.get("latency_ms", 0.0)) for e in second], 95) or 0.0
        if second_err >= 3 / len(second) and second_err > 2 * first_err:
            findings.append(
                f"error spike: 5xx rate {first_err:.3f} -> {second_err:.3f} in-window")
        if second_p95 > 1.5 * first_p95 and second_p95 > 100:
            findings.append(
                f"latency spike: p95 {first_p95:.1f}ms -> {second_p95:.1f}ms in-window")
    if error_rate >= 0.05 and total >= 10:
        findings.append(f"elevated error rate overall: {error_rate:.3f}")
    if p95 is not None and p95 > 500:
        findings.append(f"high p95 latency overall: {p95:.1f}ms")
    if not findings:
        findings.append("no anomalies: error and latency within normal bounds")

    return {
        "tool": "analyze_logs",
        "time_range": time_range,
        "requests": total,
        "error_count_5xx": len(errors),
        "error_rate_5xx": round(error_rate, 4),
        "latency_ms_p50": p50,
        "latency_ms_p95": p95,
        "by_endpoint": by_endpoint,
        "model_mix": model_mix,
        "findings": findings,
    }
