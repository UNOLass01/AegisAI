"""AegisAI evaluation harness: run the investigation agent over every scenario
in evaluation/scenarios/ and score root-cause accuracy, tool selection,
evidence grounding, report completeness, latency, and token usage.

Usage:
    python evaluation/evaluation.py
    python evaluation/evaluation.py --rag-provider hash --qdrant-url :memory:
    python evaluation/evaluation.py --limit 2   # smoke test subset

Writes evaluation/results/latest.json and prints a scorecard table.
"""
import argparse
import datetime
import json
import os
import sys
import time
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
# Backend sources live in <root>/backend (repo checkout) or <root>/app
# (backend container, where the build context root is copied to /code).
for _candidate in (REPO_ROOT / "backend", REPO_ROOT):
    if (_candidate / "app").is_dir():
        sys.path.insert(0, str(_candidate))
        break

from app.agents import investigation_agent  # noqa: E402
from app.agents.investigation_agent import run_investigation  # noqa: E402
from app.rag.embeddings import get_provider  # noqa: E402
from app.rag.ingest import ensure_ingested  # noqa: E402
from app.rag.store import get_client  # noqa: E402
from app.services.logger import log_buffer, record_log_entry  # noqa: E402

RESULTS_DIR = REPO_ROOT / "evaluation" / "results"
KNOWN_KEYS = {"data_drift", "labeling_error", "infra_latency", "undetermined"}


# --- loading ---


def load_scenarios(scenarios_dir: str | Path) -> list[dict]:
    scenarios = []
    for path in sorted(Path(scenarios_dir).glob("*.yaml")):
        with open(path, encoding="utf-8") as fh:
            scenario = yaml.safe_load(fh)
        for field in ("id", "problem", "injected_condition",
                      "expected_root_cause", "expected_tools_used"):
            if field not in scenario:
                raise ValueError(f"{path.name} missing {field!r}")
        if scenario["expected_root_cause"]["key"] not in KNOWN_KEYS:
            raise ValueError(f"{path.name} has unknown root-cause key")
        scenarios.append(scenario)
    if not scenarios:
        raise ValueError(f"no scenarios in {scenarios_dir}")
    return scenarios


# --- condition seeding ---


def _seed_entry(minutes_ago: float, latency_ms: float, status: int = 200) -> dict:
    ts = (datetime.datetime.now(datetime.timezone.utc)
          - datetime.timedelta(minutes=minutes_ago)).isoformat()
    return {"timestamp": ts, "endpoint": "/predict", "method": "POST",
            "model_version": "v1", "latency_ms": latency_ms,
            "status_code": status}


def apply_condition(condition: dict) -> callable:
    """Swap the log buffer for scenario-seeded entries; returns restore fn."""
    saved = list(log_buffer)
    log_buffer.clear()
    try:
        cond_type = condition.get("type", "model_state")
        if cond_type == "log_spike":
            for name in ("fast", "slow"):
                spec = condition[name]
                n = int(spec["n"])
                span = float(spec["minutes_ago_start"]) - float(spec["minutes_ago_end"])
                for i in range(n):
                    minutes_ago = float(spec["minutes_ago_end"]) + span * (i / max(n - 1, 1))
                    record_log_entry(_seed_entry(minutes_ago, float(spec["latency_ms"])))
        elif cond_type != "model_state":
            raise ValueError(f"unknown injected_condition type {cond_type!r}")
    except Exception:
        log_buffer.extend(saved)
        raise

    def restore() -> None:
        log_buffer.clear()
        log_buffer.extend(saved)

    return restore


# --- scoring ---


def score_root_cause(hypothesis_key: str, hypothesis_text: str,
                     expected: dict) -> float:
    if hypothesis_key == expected["key"]:
        return 1.0
    text = (hypothesis_text or "").lower()
    if any(kw.lower() in text for kw in expected.get("keywords", [])):
        return 1.0
    return 0.0


def score_tools(report, expected_tools: list[str]) -> float:
    if not expected_tools:
        return 1.0
    used = {e.tool for e in report.evidence}
    return round(len(set(expected_tools) & used) / len(expected_tools), 4)


def score_grounding(report) -> tuple[float, list[str]]:
    """Fraction of evidence items with a real summary + source attribution."""
    ungrounded = []
    for item in report.evidence:
        ok_summary = len(item.summary or "") > 10
        ok_source = bool(item.source)
        ok_score = item.score is not None or item.tool != "search_knowledge"
        if not (ok_summary and ok_source and ok_score):
            ungrounded.append(f"[{item.tool}] {item.summary[:80]}")
    total = len(report.evidence)
    return (round((total - len(ungrounded)) / total, 4) if total else 0.0,
            ungrounded)


def score_completeness(report) -> float:
    checks = [
        bool(report.investigation_id),
        bool(report.status),
        len(report.finding_summary or "") >= 20,
        len(report.evidence) >= 3,
        len(report.root_cause_hypothesis or "") >= 10,
        0.0 <= float(report.confidence or -1) <= 1.0,
        sum(1 for a in (report.recommended_actions or []) if a.strip()) >= 2,
    ]
    return round(sum(1 for c in checks if c) / len(checks), 4)


# --- runner ---


def run_harness(scenarios: list[dict], ingest: bool = True) -> dict:
    if ingest:
        ensure_ingested()
    per_scenario = []
    for scenario in scenarios:
        restore = apply_condition(scenario.get("injected_condition", {}))
        try:
            started = time.perf_counter()
            report = run_investigation(scenario["problem"])
            latency_s = round(time.perf_counter() - started, 3)
            info = dict(investigation_agent.last_run_info)
        finally:
            restore()
        usage = info.get("llm_usage", {}) if isinstance(info, dict) else {}
        grounding, ungrounded = score_grounding(report)
        per_scenario.append({
            "id": scenario["id"],
            "problem": scenario["problem"],
            "expected_root_cause": scenario["expected_root_cause"]["key"],
            "predicted_key": info.get("hypothesis_key", ""),
            "root_cause_accuracy": score_root_cause(
                info.get("hypothesis_key", ""), report.root_cause_hypothesis,
                scenario["expected_root_cause"]),
            "tool_selection": score_tools(report, scenario["expected_tools_used"]),
            "evidence_grounding": grounding,
            "ungrounded_claims": ungrounded,
            "report_completeness": score_completeness(report),
            "latency_s": latency_s,
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "llm_kind": usage.get("llm_kind", "unknown"),
            "confidence": report.confidence,
        })
    return {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "n_scenarios": len(per_scenario),
        "summary": summarize(per_scenario),
        "scenarios": per_scenario,
    }


def summarize(rows: list[dict]) -> dict:
    def mean(key: str) -> float:
        return round(sum(r[key] for r in rows) / len(rows), 4) if rows else 0.0

    return {
        "root_cause_accuracy": mean("root_cause_accuracy"),
        "tool_selection": mean("tool_selection"),
        "evidence_grounding": mean("evidence_grounding"),
        "report_completeness": mean("report_completeness"),
        "avg_latency_s": mean("latency_s"),
        "avg_tokens": round(sum(r["prompt_tokens"] + r["completion_tokens"]
                                for r in rows) / len(rows), 1) if rows else 0.0,
    }


def print_scorecard(results: dict) -> None:
    summary = results["summary"]

    def pct(value: float) -> str:
        return f"{value * 100:.0f}%"

    print(f"Scenarios                 {results['n_scenarios']}")
    print(f"Root cause accuracy       {pct(summary['root_cause_accuracy'])}")
    print(f"Evidence grounding        {pct(summary['evidence_grounding'])}")
    print(f"Tool selection            {pct(summary['tool_selection'])}")
    print(f"Report completeness       {pct(summary['report_completeness'])}")
    print(f"Avg latency               {summary['avg_latency_s']:.1f}s")
    print(f"Avg tokens                {summary['avg_tokens']:,.0f}")
    print()
    print(f"{'id':12s} {'expected':15s} {'predicted':15s} {'rc':3s} "
          f"{'ground':6s} {'lat(s)':6s}")
    for row in results["scenarios"]:
        print(f"{row['id']:12s} {row['expected_root_cause']:15s} "
              f"{row['predicted_key']:15s} {row['root_cause_accuracy']:<3.0f} "
              f"{row['evidence_grounding']:<6.2f} {row['latency_s']:<6.1f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the evaluation harness.")
    parser.add_argument("--scenarios-dir", default=str(REPO_ROOT / "evaluation" / "scenarios"))
    parser.add_argument("--out", default=str(RESULTS_DIR / "latest.json"))
    parser.add_argument("--rag-provider", default=None,
                        help="Embedding provider (default: EMBEDDING_PROVIDER env or local).")
    parser.add_argument("--qdrant-url", default=None,
                        help="Qdrant URL or :memory: (default: QDRANT_URL env).")
    parser.add_argument("--limit", type=int, default=None,
                        help="Run only the first N scenarios (smoke test).")
    parser.add_argument("--skip-ingest", action="store_true")
    args = parser.parse_args()

    if args.rag_provider:
        os.environ["EMBEDDING_PROVIDER"] = args.rag_provider
    if args.qdrant_url:
        os.environ["QDRANT_URL"] = args.qdrant_url
    # Resolve provider/client eagerly so misconfiguration fails fast.
    get_provider()
    get_client()

    scenarios = load_scenarios(args.scenarios_dir)
    if args.limit:
        scenarios = scenarios[: args.limit]
    results = run_harness(scenarios, ingest=not args.skip_ingest)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2))
    print(f"wrote {out_path}")
    print_scorecard(results)


if __name__ == "__main__":
    main()
