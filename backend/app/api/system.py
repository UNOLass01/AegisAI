"""Backend-proxied system summary for the Overview page (single call).

Live serving numbers come from Prometheus; the investigation count from
Postgres. When Prometheus is unreachable the metric fields are null and
prometheus_reachable is False (still HTTP 200, so the UI can render
explicit unavailable states).
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.investigation import Investigation
from app.services.database import get_db
from app.tools import prometheus as prometheus_tool

router = APIRouter(tags=["system"])

WINDOW = "5m"


class SystemSummary(BaseModel):
    request_rate_per_s: float | None
    error_share_5xx: float | None
    predict_latency_p95_s: float | None
    active_model_version: str | None
    agent_avg_step_latency_s: float | None
    investigations_total: int
    prometheus_reachable: bool


def _scalar(result: list[dict]) -> float | None:
    try:
        return float(result[0]["value"][1])
    except (ValueError, TypeError, IndexError):
        return None


def _by_label(result: list[dict], label: str) -> dict[str, float]:
    out = {}
    for item in result:
        try:
            out[item["metric"][label]] = float(item["value"][1])
        except (ValueError, TypeError, IndexError, KeyError):
            continue
    return out


def query_prometheus_summary() -> dict:
    query = prometheus_tool.prom_query
    volume = _by_label(query(
        f"sum by (model_version) (rate(aegis_predict_requests_total[{WINDOW}]))"),
        "model_version")
    latency = _by_label(query(
        "histogram_quantile(0.95, sum by (le, model_version)"
        f" (rate(aegis_predict_latency_seconds_bucket[{WINDOW}])))"),
        "model_version")
    agent_latency = _scalar(query(
        f"sum(rate(agent_step_duration_seconds_sum[{WINDOW}]))"
        f" / sum(rate(agent_step_duration_seconds_count[{WINDOW}]))"))
    return {
        "request_rate_per_s": _scalar(query(
            f"sum(rate(http_requests_total[{WINDOW}]))")),
        "error_share_5xx": _scalar(query(
            f'sum(rate(http_requests_total{{status=~"5.."}}[{WINDOW}]))'
            f" / sum(rate(http_requests_total[{WINDOW}]))")),
        "predict_latency_p95_s": max(latency.values()) if latency else None,
        "active_model_version": max(volume, key=volume.get) if volume else None,
        "agent_avg_step_latency_s": agent_latency,
    }


@router.get("/system/summary", response_model=SystemSummary)
def system_summary(db: Session = Depends(get_db)) -> dict:
    investigations_total = db.query(func.count(Investigation.id)).scalar() or 0
    try:
        metrics = query_prometheus_summary()
        reachable = True
    except Exception:
        metrics = {"request_rate_per_s": None, "error_share_5xx": None,
                   "predict_latency_p95_s": None, "active_model_version": None,
                   "agent_avg_step_latency_s": None}
        reachable = False
    return {**metrics, "investigations_total": investigations_total,
            "prometheus_reachable": reachable}
