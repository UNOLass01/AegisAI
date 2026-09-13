"""The AegisAI investigation agent — one LangGraph agent with five tools.

Graph: investigate → {get_metrics, analyze_logs, analyze_model,
search_knowledge} (fan-out) → reason → generate_report.

Evidence always comes from tool outputs (grounding by construction). The
reasoning layer is either an LLM (OpenAI-compatible / Ollama) synthesizing
the narrative, or the deterministic stub composing it from evidence signals.
"""
import json
import operator
import re
import uuid
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents import llm as llm_module
from app.agents.schemas import IncidentReport
from app.agents.tracing import Timer, make_span
from app.services.metrics import AGENT_COST, AGENT_STEP_DURATION, AGENT_TOKENS
from app.tools import knowledge_search as knowledge_tool
from app.tools import log_analysis as logs_tool
from app.tools import model_analysis as model_tool
from app.tools import prometheus as metrics_tool
from app.tools import report as report_tool

VERSION_RE = re.compile(r"\bv(\d+)\b", re.IGNORECASE)

REASON_SYSTEM_PROMPT = (
    "You are an ML production-incident investigator. Given tool outputs "
    "(metrics, logs, model evaluation deltas, knowledge-base matches), "
    "identify the most likely root cause. Respond with JSON only, keys: "
    "root_cause_hypothesis (string), confidence (0-1 number), "
    "finding_summary (string), recommended_actions (list of strings)."
)


class InvestigationState(TypedDict, total=False):
    query: str
    investigation_id: str
    focus_versions: list[str]
    time_range: str | None
    metrics: Annotated[list[dict], operator.add]
    logs: Annotated[list[dict], operator.add]
    model: Annotated[list[dict], operator.add]
    knowledge: Annotated[list[dict], operator.add]
    llm_reasoning: dict
    llm_usage: dict
    hypothesis_key: str
    spans: Annotated[list[dict], operator.add]
    report: dict | None


def extract_versions(query: str) -> list[str]:
    seen: list[str] = []
    for match in VERSION_RE.finditer(query):
        version = f"v{match.group(1)}"
        if version not in seen:
            seen.append(version)
    return seen


def investigate_node(state: InvestigationState) -> dict:
    timer = Timer()
    focus = extract_versions(state.get("query", ""))
    return {"focus_versions": focus,
            "spans": [make_span("investigate", timer.started_at,
                                timer.elapsed_ms())]}


def _focus_version(state: InvestigationState) -> str | None:
    # First mentioned version is the subject ("compare v3 against v2" -> v3).
    versions = state.get("focus_versions") or []
    return versions[0] if versions else None


def metrics_node(state: InvestigationState) -> dict:
    timer = Timer()
    try:
        result = metrics_tool.get_metrics(
            model_version=_focus_version(state),
            time_range=state.get("time_range"))
        return {"metrics": [result],
                "spans": [make_span("get_metrics", timer.started_at,
                                    timer.elapsed_ms())]}
    except Exception as exc:
        return {"metrics": [{"tool": "get_metrics", "error": str(exc)}],
                "spans": [make_span("get_metrics", timer.started_at,
                                    timer.elapsed_ms(), status="error",
                                    error=str(exc))]}


def logs_node(state: InvestigationState) -> dict:
    timer = Timer()
    try:
        result = logs_tool.analyze_logs(time_range=state.get("time_range"))
        return {"logs": [result],
                "spans": [make_span("analyze_logs", timer.started_at,
                                    timer.elapsed_ms())]}
    except Exception as exc:
        return {"logs": [{"tool": "analyze_logs", "error": str(exc)}],
                "spans": [make_span("analyze_logs", timer.started_at,
                                    timer.elapsed_ms(), status="error",
                                    error=str(exc))]}


def model_node(state: InvestigationState) -> dict:
    timer = Timer()
    try:
        result = model_tool.analyze_model(version=_focus_version(state))
        return {"model": [result],
                "spans": [make_span("analyze_model", timer.started_at,
                                    timer.elapsed_ms())]}
    except Exception as exc:
        return {"model": [{"tool": "analyze_model", "error": str(exc)}],
                "spans": [make_span("analyze_model", timer.started_at,
                                    timer.elapsed_ms(), status="error",
                                    error=str(exc))]}


def knowledge_node(state: InvestigationState) -> dict:
    timer = Timer()
    try:
        result = knowledge_tool.search_knowledge(state.get("query", ""))
        return {"knowledge": [result],
                "spans": [make_span("search_knowledge", timer.started_at,
                                    timer.elapsed_ms())]}
    except Exception as exc:
        return {"knowledge": [{"tool": "search_knowledge", "error": str(exc)}],
                "spans": [make_span("search_knowledge", timer.started_at,
                                    timer.elapsed_ms(), status="error",
                                    error=str(exc))]}


def _validate_llm_reasoning(payload: object) -> dict:
    if not isinstance(payload, dict):
        return {}
    hypothesis = payload.get("root_cause_hypothesis")
    summary = payload.get("finding_summary")
    actions = payload.get("recommended_actions")
    try:
        confidence = float(payload.get("confidence", -1))
    except (TypeError, ValueError):
        return {}
    if (not isinstance(hypothesis, str) or not hypothesis.strip()
            or not isinstance(summary, str) or not summary.strip()
            or not (0.0 <= confidence <= 1.0)
            or not isinstance(actions, list) or not actions
            or not all(isinstance(a, str) and a.strip() for a in actions)):
        return {}
    return {"root_cause_hypothesis": hypothesis.strip(),
            "confidence": confidence,
            "finding_summary": summary.strip(),
            "recommended_actions": [a.strip() for a in actions]}


def reason_node(state: InvestigationState) -> dict:
    timer = Timer()
    config = llm_module.resolve_llm()
    if config.kind == "stub":
        return {"llm_reasoning": {},
                "llm_usage": dict(config.last_usage),
                "spans": [make_span("reason", timer.started_at,
                                    timer.elapsed_ms(), model=config.model)]}
    tool_summary = {
        "metrics": (state.get("metrics") or [{}])[0],
        "logs": (state.get("logs") or [{}])[0],
        "model": (state.get("model") or [{}])[0],
        "knowledge": (state.get("knowledge") or [{}])[0],
    }
    messages = [
        {"role": "system", "content": REASON_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(
            {"query": state.get("query", ""), "tool_outputs": tool_summary})},
    ]
    try:
        payload = json.loads(llm_module.complete(config, messages, json_mode=True))
        reasoning = _validate_llm_reasoning(payload)
    except Exception:
        reasoning = {}
    usage = dict(config.last_usage)
    return {"llm_reasoning": reasoning,
            "llm_usage": usage,
            "spans": [make_span("reason", timer.started_at, timer.elapsed_ms(),
                                tokens_in=usage.get("prompt_tokens", 0),
                                tokens_out=usage.get("completion_tokens", 0),
                                model=config.model,
                                status="ok" if reasoning else "error",
                                error=None if reasoning else "llm failed; stub fallback")]}


def report_node(state: InvestigationState) -> dict:
    timer = Timer()
    findings = {
        "query": state.get("query", ""),
        "investigation_id": state.get("investigation_id", "unknown"),
        "model": (state.get("model") or [{}])[0],
        "metrics": (state.get("metrics") or [{}])[0],
        "logs": (state.get("logs") or [{}])[0],
        "knowledge": (state.get("knowledge") or [{}])[0],
        "llm_reasoning": state.get("llm_reasoning") or {},
    }
    report = report_tool.generate_report(findings)
    hypothesis_key, _, _, _ = report_tool.decide_root_cause(
        findings["model"], findings["metrics"],
        findings["logs"], findings["knowledge"])
    span = make_span("generate_report", timer.started_at, timer.elapsed_ms())
    return {"report": report.model_dump(), "hypothesis_key": hypothesis_key,
            "spans": [span]}


def build_graph():
    graph = StateGraph(InvestigationState)
    graph.add_node("investigate", investigate_node)
    graph.add_node("get_metrics", metrics_node)
    graph.add_node("analyze_logs", logs_node)
    graph.add_node("analyze_model", model_node)
    graph.add_node("search_knowledge", knowledge_node)
    graph.add_node("reason", reason_node)
    graph.add_node("generate_report", report_node)
    graph.add_edge(START, "investigate")
    for tool_node in ("get_metrics", "analyze_logs", "analyze_model",
                      "search_knowledge"):
        graph.add_edge("investigate", tool_node)
        graph.add_edge(tool_node, "reason")
    graph.add_edge("reason", "generate_report")
    graph.add_edge("generate_report", END)
    return graph.compile()


_GRAPH = None

# Info about the most recent run (latency excluded — the harness times it).
# Keys: hypothesis_key, llm_usage {llm_kind, prompt_tokens, completion_tokens},
# spans [{step, started_at, duration_ms, tokens_in/out, tokens, cost_usd, ...}].
last_run_info: dict = {}


def get_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


def run_investigation(query: str, time_range: str | None = None) -> IncidentReport:
    """Run the full graph and return a validated IncidentReport."""
    initial: InvestigationState = {
        "query": query,
        "investigation_id": uuid.uuid4().hex[:12],
        "focus_versions": [],
        "time_range": time_range,
        "metrics": [],
        "logs": [],
        "model": [],
        "knowledge": [],
        "llm_reasoning": {},
        "llm_usage": {},
        "hypothesis_key": "",
        "spans": [],
        "report": None,
    }
    final = get_graph().invoke(initial)
    spans = final.get("spans", [])
    _observe_agent_metrics(spans)
    global last_run_info
    last_run_info = {
        "hypothesis_key": final.get("hypothesis_key", ""),
        "llm_usage": final.get("llm_usage") or {},
        "spans": spans,
    }
    return IncidentReport(**final["report"])


def _observe_agent_metrics(spans: list[dict]) -> None:
    """Export per-step timings, token totals, and cost to Prometheus."""
    tokens_in = sum(int(s.get("tokens_in", 0)) for s in spans)
    tokens_out = sum(int(s.get("tokens_out", 0)) for s in spans)
    for span in spans:
        AGENT_STEP_DURATION.labels(step=span.get("step", "?")).observe(
            float(span.get("duration_ms", 0.0)) / 1000.0)
    # Unconditional incs so the series exist (as zeros) even for stub runs.
    AGENT_TOKENS.labels(direction="in").inc(tokens_in)
    AGENT_TOKENS.labels(direction="out").inc(tokens_out)
    AGENT_COST.inc(round(sum(float(s.get("cost_usd", 0.0)) for s in spans), 6))
