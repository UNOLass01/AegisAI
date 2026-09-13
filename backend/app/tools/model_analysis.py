"""Tool: analyze_model — offline metric deltas between model versions.

Reads the ML evaluation reports (ml/evaluation/reports/) and compares the
requested version against its predecessor, flagging precision drops, recall
drops, false-positive rises, and training-data changes.
"""
from app.services.model_store import available_versions, get_metrics

PRECISION_DROP_THRESHOLD = -0.05
RECALL_DROP_THRESHOLD = -0.10


def _previous_version(version: str, versions: list[str]) -> str | None:
    ordered = sorted(versions)
    try:
        index = ordered.index(version)
    except ValueError:
        return None
    return ordered[index - 1] if index > 0 else None


def analyze_model(version: str | None = None) -> dict:
    """Compare a version's report against its predecessor (default: latest)."""
    versions = available_versions()
    if not versions:
        return {"tool": "analyze_model", "error": "no model versions found"}
    focus = version or sorted(versions)[-1]
    baseline = _previous_version(focus, versions)
    current = get_metrics(focus)
    if current is None:
        return {"tool": "analyze_model", "error": f"no metrics report for {focus!r}"}
    result: dict = {
        "tool": "analyze_model",
        "version": focus,
        "baseline_version": baseline,
        "metrics": current,
        "deltas": {},
        "flags": [],
    }
    if baseline is None:
        result["flags"].append(f"{focus} is the first version; nothing to compare")
        return result
    previous = get_metrics(baseline) or {}
    deltas = {}
    for key in ("accuracy", "precision", "recall", "f1"):
        if key in current and key in previous:
            deltas[key] = round(float(current[key]) - float(previous[key]), 4)
    for key in ("false_positives", "false_negatives", "true_positives"):
        if key in current and key in previous:
            deltas[key] = int(current[key]) - int(previous[key])
    result["deltas"] = deltas

    flags = result["flags"]
    if deltas.get("precision", 0.0) <= PRECISION_DROP_THRESHOLD:
        flags.append(
            f"precision drop {previous.get('precision')} -> {current.get('precision')}")
    if deltas.get("recall", 0.0) <= RECALL_DROP_THRESHOLD:
        flags.append(
            f"recall drop {previous.get('recall')} -> {current.get('recall')}")
    if deltas.get("false_positives", 0) > 0:
        flags.append(
            f"false positives rose {previous.get('false_positives')} -> "
            f"{current.get('false_positives')}")
    if deltas.get("false_negatives", 0) > 0:
        flags.append(
            f"false negatives rose {previous.get('false_negatives')} -> "
            f"{current.get('false_negatives')}")
    if current.get("dataset_version") != previous.get("dataset_version"):
        flags.append(
            f"training/eval data changed {previous.get('dataset_version')} -> "
            f"{current.get('dataset_version')}")
    if not flags:
        flags.append("no significant regression vs baseline")
    return result
