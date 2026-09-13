"""Investigation endpoint: run the agent and persist the report."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agents.investigation_agent import run_investigation
from app.agents.schemas import IncidentReport
from app.models.investigation import Investigation
from app.services.database import get_db
from app.tools.log_analysis import parse_time_range

router = APIRouter(tags=["investigations"])


class InvestigateRequest(BaseModel):
    query: str = Field(min_length=3, max_length=2000)
    time_range: str | None = Field(default=None, max_length=10)


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
    db.commit()
    return report
