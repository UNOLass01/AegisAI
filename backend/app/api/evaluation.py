"""Evaluation results endpoint: serve the latest harness scorecard."""
import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["evaluation"])


def _results_dir() -> Path:
    override = os.getenv("EVALUATION_RESULTS_DIR")
    if override:
        return Path(override)
    for ancestor in Path(__file__).resolve().parents:
        candidate = ancestor / "evaluation" / "results"
        if (ancestor / "evaluation").is_dir():
            return candidate
    raise FileNotFoundError("evaluation/results directory not found")


@router.get("/evaluation/latest")
def evaluation_latest() -> dict:
    path = _results_dir() / "latest.json"
    if not path.exists():
        raise HTTPException(status_code=404,
                            detail="no evaluation results yet; run evaluation/evaluation.py")
    return json.loads(path.read_text())
