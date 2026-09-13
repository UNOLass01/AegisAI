"""Tool: get_metrics — query Prometheus for serving metrics.

Covers request count, latency (p95), error share, per-version prediction
volume, and the precision proxy (true positives / flagged) per version.

Falls back from PROMETHEUS_URL to localhost; on total failure returns an
{"error": ...} payload instead of raising so the agent keeps working.
"""
import os

import httpx

DEFAULT_URL = "http://prometheus:9090"
LOCAL_FALLBACK_URL = "http://localhost:9090"
QUERY_TIMEOUT_S = 10.0


def _base_urls() -> list[str]:
    configured = os.getenv("PROMETHEUS_URL", DEFAULT_URL)
    urls = [configured.rstrip("/")]
    if urls[0] != LOCAL_FALLBACK_URL:
        urls.append(LOCAL_FALLBACK_URL)
    return urls


def prom_query(expr: str) -> list[dict]:
    """Run an instant PromQL query, trying each candidate base URL in turn."""
    errors = []
    for base in _base_urls():
        try:
            resp = httpx.get(f"{base}/api/v1/query", params={"query": expr},
                             timeout=QUERY_TIMEOUT_S)
            resp.raise_for_status()
            return resp.json()["data"]["result"]
        except Exception as exc:
            errors.append(f"{base}: {exc}")
    raise ConnectionError(f"Prometheus unreachable ({'; '.join(errors)})")


def _by_label(result: list[dict], label: str) -> dict[str, float]:
    out = {}
    for item in result:
        key = item["metric"].get(label, "?")
        try:
            out[key] = float(item["value"][1])
        except (ValueError, TypeError, IndexError):
            continue
    return out


def _scalar(result: list[dict]) -> float | None:
    try:
        return float(result[0]["value"][1])
    except (ValueError, TypeError, IndexError):
        return None


def get_metrics(
    model_version: str | None = None, time_range: str | None = None
) -> dict:
    """Fetch serving metrics. model_version narrows per-version panels."""
    window = time_range or "15m"
    version_filter = (
        f'{{model_version="{model_version}"}}' if model_version else ""
    )
    try:
        precision = _by_label(
            prom_query(
                f"sum by (model_version) (rate(aegis_predict_true_positives_total[{window}]))"
                f" / sum by (model_version) (rate(aegis_predict_flagged_total[{window}]))"
            ),
            "model_version",
        )
        volume = _by_label(
            prom_query(
                f"sum by (model_version) (rate(aegis_predict_requests_total[{window}]))"
            ),
            "model_version",
        )
        latency = _by_label(
            prom_query(
                "histogram_quantile(0.95, sum by (le, model_version)"
                f" (rate(aegis_predict_latency_seconds_bucket[{window}])))"
            ),
            "model_version",
        )
        error_share = _scalar(
            prom_query(
                f'sum(rate(http_requests_total{{status=~"5.."}}[{window}]))'
                f" / sum(rate(http_requests_total[{window}]))"
            )
        )
        request_rate = _by_label(
            prom_query(f"sum by (handler) (rate(http_requests_total[{window}]))"),
            "handler",
        )
    except Exception as exc:
        return {"tool": "get_metrics", "error": str(exc), "time_range": window}
    result = {
        "tool": "get_metrics",
        "time_range": window,
        "precision_by_version": precision,
        "request_volume_by_version": volume,
        "p95_latency_s_by_version": latency,
        "error_share_5xx": error_share,
        "request_rate_by_handler": request_rate,
    }
    if model_version:
        result["focus_version"] = model_version
        for key in ("precision_by_version", "request_volume_by_version",
                    "p95_latency_s_by_version"):
            result[key] = {model_version: result[key].get(model_version)}
    return result
