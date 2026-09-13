"""Tool: generate_report — compose the final structured IncidentReport.

Evidence is ALWAYS assembled deterministically from tool outputs (grounding
by construction). The reasoning layer (LLM synthesis or the deterministic
stub) only supplies the narrative: hypothesis, confidence, summary,
recommended actions.
"""
from app.agents.schemas import EvidenceItem, IncidentReport

RECOMMENDED_ACTIONS = {
    "data_drift": [
        "Roll back serving traffic to v1 while legitimate spending is elevated.",
        "Add a distribution-drift monitor on transaction_amount (e.g. weekly PSI).",
        "Recalibrate the decision threshold per regime instead of blind retraining.",
        "Never retrain on unreviewed drifted data without a holdout comparison.",
    ],
    "labeling_error": [
        "Roll back to v1 and quarantine the corrupted training export.",
        "Add a label-distribution check to the training pipeline (fraud-rate guard).",
        "Gate fraud-model promotions on recall, not accuracy.",
        "Keep per-version training-data manifests so bad exports are traceable.",
    ],
    "infra_latency": [
        "Throttle replay concurrency and add backend replicas for peak windows.",
        "Keep latency alerts separate from precision alerts to avoid ML blame.",
        "Load-test before doubling replay traffic again.",
    ],
    "undetermined": [
        "Collect more traffic over a wider time window and re-run this investigation.",
        "Re-run offline evaluation for all model versions before promoting.",
        "Check upstream data pipelines for silent schema or volume changes.",
    ],
}


def _flags(model: dict) -> list[str]:
    return list(model.get("flags", []))


def _top_kb_incident(knowledge: dict) -> str | None:
    hits = knowledge.get("hits", [])
    return hits[0].get("incident_id") if hits else None


def decide_root_cause(model: dict, metrics: dict, logs: dict,
                      knowledge: dict) -> tuple[str, float, list[str], str | None]:
    """Evidence-driven hypothesis selection.

    Returns (hypothesis_key, confidence, corroborating_signals, kb_source).
    """
    flags = _flags(model)
    text_flags = " | ".join(flags).lower()
    precision_drop = "precision drop" in text_flags
    fp_rise = "false positives rose" in text_flags
    recall_drop = "recall drop" in text_flags
    fn_rise = "false negatives rose" in text_flags
    dataset_change = "data changed" in text_flags
    dataset_text = f"{model.get('metrics', {}).get('dataset_version', '')}".lower()

    kb_top = _top_kb_incident(knowledge)

    precisions = metrics.get("precision_by_version", {}) or {}
    precision_gap = False
    if len(precisions) >= 2:
        values = [v for v in precisions.values() if v is not None]
        if values and max(values) - min(values) > 0.03:
            precision_gap = True

    log_findings = " | ".join(logs.get("findings", [])).lower()
    latency_spike = "latency spike" in log_findings or "high p95" in log_findings

    scores = {"data_drift": 0, "labeling_error": 0, "infra_latency": 0}
    signals: dict[str, list[str]] = {"data_drift": [], "labeling_error": [],
                                     "infra_latency": []}
    if precision_drop:
        scores["data_drift"] += 2
        signals["data_drift"].append("offline precision drop vs baseline")
    if fp_rise:
        scores["data_drift"] += 2
        signals["data_drift"].append("offline false-positive rise")
    if dataset_change and "drift" in dataset_text:
        scores["data_drift"] += 2
        signals["data_drift"].append("training/eval data drift recorded")
    if kb_top == "011":
        scores["data_drift"] += 2
        signals["data_drift"].append("knowledge base matches Incident #011 (drift)")
    if precision_gap:
        scores["data_drift"] += 1
        signals["data_drift"].append("live precision differs across versions")
    if recall_drop:
        scores["labeling_error"] += 2
        signals["labeling_error"].append("offline recall drop vs baseline")
    if fn_rise:
        scores["labeling_error"] += 2
        signals["labeling_error"].append("offline false-negative rise")
    if kb_top == "014":
        scores["labeling_error"] += 2
        signals["labeling_error"].append("knowledge base matches Incident #014 (labels)")
    if latency_spike:
        # Live production anomaly: weighs more than stale offline deltas so a
        # measured in-window spike decides latency scenarios even when an old
        # recall regression is also on record.
        scores["infra_latency"] += 3
        signals["infra_latency"].append("log latency anomaly")
    if kb_top == "009":
        scores["infra_latency"] += 2
        signals["infra_latency"].append("knowledge base matches Incident #009 (latency)")
    if not precision_drop and not recall_drop and latency_spike:
        scores["infra_latency"] += 1
        signals["infra_latency"].append("latency anomaly without metric regression")

    priority = ["data_drift", "labeling_error", "infra_latency"]
    best = max(priority, key=lambda h: (scores[h], -priority.index(h)))
    if scores[best] == 0:
        return ("undetermined", 0.40, ["no corroborating signals"], None)
    # Cite the top hit supporting the decided hypothesis (falls back to top hit).
    wanted = {"data_drift": "011", "labeling_error": "014",
              "infra_latency": "009"}[best]
    kb_source = None
    for hit in knowledge.get("hits", []):
        if hit.get("incident_id") == wanted:
            kb_source = f"{hit.get('title')} ({hit.get('source')})"
            break
    if kb_source is None and knowledge.get("hits"):
        first = knowledge["hits"][0]
        kb_source = f"{first.get('title')} ({first.get('source')})"
    confidence = round(min(0.55 + 0.09 * len(signals[best]), 0.92), 2)
    return (best, confidence, signals[best], kb_source)


HYPOTHESIS_TEXT = {
    "data_drift": (
        "Data drift in transaction_amount: legitimate spending shifted upward "
        "into the fraud-associated range, degrading precision and raising "
        "false positives."
    ),
    "labeling_error": (
        "Training labeling error: corrupted fraud labels taught the model to "
        "treat fraud patterns as legitimate, collapsing recall."
    ),
    "infra_latency": (
        "Infrastructure overload (not model degradation): elevated concurrency "
        "raised serving latency while model quality metrics stayed flat."
    ),
    "undetermined": (
        "Undetermined: tool signals are weak or conflicting; no single root "
        "cause is supported by the evidence."
    ),
}


def _model_evidence(model: dict) -> EvidenceItem:
    version = model.get("version", "?")
    flags = _flags(model)
    if model.get("error"):
        return EvidenceItem(tool="analyze_model",
                            summary=f"model analysis unavailable: {model['error']}")
    return EvidenceItem(
        tool="analyze_model",
        summary=f"{version} vs baseline {model.get('baseline_version')}: "
                + "; ".join(flags[:4]),
        source=f"ml/evaluation/reports/model_{version}.json",
        details={"deltas": model.get("deltas", {})},
    )


def _metrics_evidence(metrics: dict) -> EvidenceItem:
    if metrics.get("error"):
        return EvidenceItem(tool="get_metrics",
                            summary=f"live metrics unavailable: {metrics['error']}",
                            source="prometheus")
    parts = []
    precisions = metrics.get("precision_by_version", {}) or {}
    if precisions:
        parts.append("live precision " + ", ".join(
            f"{v}={p:.3f}" for v, p in sorted(precisions.items())
            if p is not None))
    volume = metrics.get("request_volume_by_version", {}) or {}
    if volume:
        parts.append("volume req/s " + ", ".join(
            f"{v}={r:.2f}" for v, r in sorted(volume.items())
            if r is not None))
    latency = metrics.get("p95_latency_s_by_version", {}) or {}
    if latency:
        parts.append("p95 latency " + ", ".join(
            f"{v}={s:.3f}s" for v, s in sorted(latency.items())
            if s is not None))
    if metrics.get("error_share_5xx") is not None:
        parts.append(f"5xx share {metrics['error_share_5xx']:.4f}")
    return EvidenceItem(
        tool="get_metrics",
        summary="; ".join(parts) or "no live traffic in window",
        source="prometheus",
        details={"time_range": metrics.get("time_range")},
    )


def _logs_evidence(logs: dict) -> EvidenceItem:
    p95 = logs.get("latency_ms_p95")
    p95_text = f"{p95}ms" if p95 is not None else "n/a"
    return EvidenceItem(
        tool="analyze_logs",
        summary=f"{logs.get('requests', 0)} requests, "
                f"5xx rate {logs.get('error_rate_5xx')}, "
                f"p95 {p95_text}; "
                + "; ".join(logs.get("findings", [])[:3]),
        source="backend structured logs",
        details={"by_endpoint": logs.get("by_endpoint", {}),
                 "model_mix": logs.get("model_mix", {})},
    )


def _knowledge_evidence(knowledge: dict) -> list[EvidenceItem]:
    items = []
    for hit in knowledge.get("hits", [])[:3]:
        items.append(EvidenceItem(
            tool="search_knowledge",
            summary=f"matched '{hit.get('title')}'",
            source=hit.get("source"),
            score=hit.get("score"),
            details={"incident_id": hit.get("incident_id")},
        ))
    if not items:
        items.append(EvidenceItem(tool="search_knowledge",
                                  summary="no relevant knowledge chunks found"))
    return items


def generate_report(findings: dict) -> IncidentReport:
    """Compose the IncidentReport from tool findings + reasoning overlay.

    findings keys: query, investigation_id, model, metrics, logs, knowledge,
    plus optional llm_reasoning {root_cause_hypothesis, confidence,
    finding_summary, recommended_actions}.
    """
    model = findings.get("model", {})
    metrics = findings.get("metrics", {})
    logs = findings.get("logs", {})
    knowledge = findings.get("knowledge", {})
    llm_reasoning = findings.get("llm_reasoning") or {}

    evidence = [_model_evidence(model), _metrics_evidence(metrics),
                _logs_evidence(logs), *_knowledge_evidence(knowledge)]

    stub_key, stub_conf, stub_signals, kb_source = decide_root_cause(
        model, metrics, logs, knowledge)
    hypothesis = llm_reasoning.get("root_cause_hypothesis") or HYPOTHESIS_TEXT[stub_key]
    confidence = llm_reasoning.get("confidence", stub_conf)
    try:
        confidence = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        confidence = stub_conf

    if llm_reasoning.get("finding_summary"):
        summary = llm_reasoning["finding_summary"]
    else:
        model_flags = "; ".join(_flags(model)[:3])
        kb_part = f" Knowledge match: {kb_source}." if kb_source else ""
        summary = (f"{model_flags}.{kb_part} "
                   f"Corroborating signals ({len(stub_signals)}): "
                   + "; ".join(stub_signals) + ".").strip()

    actions = llm_reasoning.get("recommended_actions") or list(RECOMMENDED_ACTIONS[stub_key])
    if kb_source and not any("knowledge" in a.lower() for a in actions):
        actions = actions + [f"See knowledge base: {kb_source}."]

    return IncidentReport(
        investigation_id=findings.get("investigation_id", "unknown"),
        status="complete",
        finding_summary=summary,
        evidence=evidence,
        root_cause_hypothesis=hypothesis,
        confidence=round(confidence, 2),
        recommended_actions=actions,
    )
