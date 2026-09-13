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


class InvestigationRow(BaseModel):
    id: int
    investigation_id: str | None
    query: str
    status: str
    root_cause: str | None
    confidence: float | None
    created_at: str
    evidence_count: int


class InvestigationDetail(InvestigationRow):
    report: dict | None
    trace: list[TraceSpan]


def _row_to_summary(row: Investigation) -> dict:
    report = row.report_json or {}
    evidence = report.get("evidence", []) if isinstance(report, dict) else []
    return {
        "id": row.id,
        "investigation_id": report.get("investigation_id") if isinstance(report, dict) else None,
        "query": row.query,
        "status": row.status,
        "root_cause": row.root_cause,
        "confidence": row.confidence,
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "evidence_count": len(evidence),
    }


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


@router.get("/investigations", response_model=list[InvestigationRow])
def list_investigations(limit: int = 20, db: Session = Depends(get_db)) -> list[dict]:
    limit = max(1, min(limit, 100))
    rows = (db.query(Investigation)
            .order_by(Investigation.id.desc())
            .limit(limit)
            .all())
    return [_row_to_summary(row) for row in rows]


@router.get("/investigations/{investigation_id}", response_model=InvestigationDetail)
def investigation_detail(investigation_id: int,
                         db: Session = Depends(get_db)) -> dict:
    row = db.query(Investigation).filter(Investigation.id == investigation_id).first()
    if row is None:
        raise HTTPException(status_code=404,
                            detail=f"unknown investigation {investigation_id!r}")
    summary = _row_to_summary(row)
    trace: list[dict] = []
    hex_id = summary["investigation_id"]
    if hex_id:
        trace_rows = (db.query(AgentTrace)
                      .filter(AgentTrace.investigation_id == hex_id)
                      .order_by(AgentTrace.timestamp, AgentTrace.id)
                      .all())
        trace = [{"step": r.step, "duration_ms": r.duration_ms, "tokens": r.tokens,
                  "cost_usd": r.cost_usd, "timestamp": r.timestamp.isoformat()}
                 for r in trace_rows]
    return {**summary,
            "report": row.report_json,
            "trace": trace}


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
