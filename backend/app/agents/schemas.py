"""Pydantic schemas for agent outputs."""
from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    tool: str
    summary: str
    source: str | None = None
    score: float | None = None
    details: dict = Field(default_factory=dict)


class IncidentReport(BaseModel):
    investigation_id: str
    status: str
    finding_summary: str
    evidence: list[EvidenceItem]
    root_cause_hypothesis: str
    confidence: float = Field(ge=0.0, le=1.0)
    recommended_actions: list[str]
