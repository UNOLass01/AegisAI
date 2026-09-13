"""Past incidents from the knowledge base (file-backed, full markdown on detail)."""
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(tags=["incidents"])

TITLE_RE = re.compile(r"^#\s+(.*)")
FIELD_RES = {
    "date": re.compile(r"^- \*\*Date:\*\*\s*(.*)"),
    "severity": re.compile(r"^- \*\*Severity:\*\*\s*(.*)"),
    "model": re.compile(r"^- \*\*Model:\*\*\s*(.*)"),
    "affected": re.compile(r"^- \*\*Affected:\*\*\s*(.*)"),
    "status": re.compile(r"^- \*\*Status:\*\*\s*(.*)"),
}
INCIDENT_ID_RE = re.compile(r"incident\s*#?\s*(\d+)", re.IGNORECASE)
FILENAME_ID_RE = re.compile(r"incident-(\d+)")


def find_incidents_dir() -> Path:
    for ancestor in Path(__file__).resolve().parents:
        candidate = ancestor / "knowledge" / "incidents"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("knowledge/incidents directory not found")


def parse_incident(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    title = path.stem
    fields: dict[str, str | None] = {"affected": None, "status": "open"}
    for line in text.splitlines():
        stripped = line.strip()
        title_match = TITLE_RE.match(stripped)
        if title_match and title == path.stem:
            title = title_match.group(1).strip()
        for name, regex in FIELD_RES.items():
            match = regex.match(stripped)
            if match:
                fields[name] = match.group(1).strip()
    incident_id = None
    for source in (title, path.stem):
        match = (INCIDENT_ID_RE.search(source) or FILENAME_ID_RE.search(source))
        if match:
            incident_id = match.group(1)
            break
    return {
        "id": incident_id or path.stem,
        "title": title,
        "affected_feature": fields["affected"],
        "status": (fields["status"] or "open").lower(),
        "date": fields.get("date"),
        "severity": fields.get("severity"),
        "model": fields.get("model"),
        "source": f"knowledge/incidents/{path.name}",
    }


def list_incidents() -> list[dict]:
    rows = [parse_incident(p)
            for p in sorted(find_incidents_dir().glob("*.md"))]
    return sorted(rows, key=lambda r: r["id"])


class IncidentRow(BaseModel):
    id: str
    title: str
    affected_feature: str | None
    status: str
    date: str | None = None
    severity: str | None = None
    model: str | None = None
    source: str


class IncidentDetail(IncidentRow):
    markdown: str


@router.get("/incidents", response_model=list[IncidentRow])
def get_incidents() -> list[dict]:
    try:
        return list_incidents()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/incidents/{incident_id}", response_model=IncidentDetail)
def get_incident(incident_id: str) -> dict:
    for path in sorted(find_incidents_dir().glob("*.md")):
        row = parse_incident(path)
        if row["id"] == incident_id:
            return {**row, "markdown": path.read_text(encoding="utf-8")}
    raise HTTPException(status_code=404,
                        detail=f"unknown incident {incident_id!r}")
