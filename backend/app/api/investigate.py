"""Investigation endpoint: run the agent and persist the report + trace."""
import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agents import investigation_agent as agent_module
from app.agents.investigation_agent import run_investigation
from app.agents.schemas import IncidentReport
from app.models.agent_trace import AgentTrace
from app.models.investigation import Investigation
from app.services.database import get_db
from app.tools.log_analysis import parse_time_range

router = APIRouter(tags=["investigations"])


class InvestigateRequest(BaseModel):
    query: str = Field(min_length=3, max_length=2000)
    time_range: str | None = Field(default=None, max_length=10)


class TraceSpan(BaseModel):
    step: str
    duration_ms: float
    tokens: int
    cost_usd: float
    timestamp: str


class InvestigationTrace(BaseModel):
    investigation_id: str
    spans: list[TraceSpan]


@router.post("/investigate", response_model=IncidentReport)
def investigate(body: InvestigateRequest, db: Session = Depends(get_db)) -> IncidentReport:
    try:
        parse_time_range(body.time_range)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        report = run_investigation(body.query, time_range=body.time_range)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"investigation failed: {exc}") from exc
    db.add(Investigation(
        query=body.query,
        status=report.status,
        root_cause=report.root_cause_hypothesis,
        confidence=report.confidence,
        report_json=report.model_dump(),
    ))
    for span in agent_module.last_run_info.get("spans", []):
        db.add(AgentTrace(
            investigation_id=report.investigation_id,
            step=span.get("step", "?"),
            duration_ms=float(span.get("duration_ms", 0.0)),
            tokens=int(span.get("tokens", 0)),
            cost_usd=float(span.get("cost_usd", 0.0)),
            timestamp=datetime.datetime.fromisoformat(span["started_at"]),
        ))
    db.commit()
    return report


@router.get("/investigations/{investigation_id}/trace",
            response_model=InvestigationTrace)
def investigation_trace(investigation_id: str,
                        db: Session = Depends(get_db)) -> dict:
    rows = (db.query(AgentTrace)
            .filter(AgentTrace.investigation_id == investigation_id)
            .order_by(AgentTrace.timestamp, AgentTrace.id)
            .all())
    if not rows:
        raise HTTPException(status_code=404,
                            detail=f"no trace for investigation {investigation_id!r}")
    return {
        "investigation_id": investigation_id,
        "spans": [
            {"step": row.step, "duration_ms": row.duration_ms,
             "tokens": row.tokens, "cost_usd": row.cost_usd,
             "timestamp": row.timestamp.isoformat()}
            for row in rows
        ],
    }
