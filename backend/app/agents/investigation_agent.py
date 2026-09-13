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
    report: dict | None


def extract_versions(query: str) -> list[str]:
    seen: list[str] = []
    for match in VERSION_RE.finditer(query):
        version = f"v{match.group(1)}"
        if version not in seen:
            seen.append(version)
    return seen


def investigate_node(state: InvestigationState) -> dict:
    return {"focus_versions": extract_versions(state.get("query", ""))}


def _focus_version(state: InvestigationState) -> str | None:
    versions = state.get("focus_versions") or []
    return versions[-1] if versions else None


def metrics_node(state: InvestigationState) -> dict:
    return {"metrics": [metrics_tool.get_metrics(
        model_version=_focus_version(state),
        time_range=state.get("time_range"))]}


def logs_node(state: InvestigationState) -> dict:
    return {"logs": [logs_tool.analyze_logs(time_range=state.get("time_range"))]}


def model_node(state: InvestigationState) -> dict:
    return {"model": [model_tool.analyze_model(version=_focus_version(state))]}


def knowledge_node(state: InvestigationState) -> dict:
    return {"knowledge": [knowledge_tool.search_knowledge(state.get("query", ""))]}


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
    config = llm_module.resolve_llm()
    if config.kind == "stub":
        return {"llm_reasoning": {}}
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
    payload = llm_module.try_complete_json(config, messages)
    return {"llm_reasoning": _validate_llm_reasoning(payload)}


def report_node(state: InvestigationState) -> dict:
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
    return {"report": report.model_dump()}


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
        "report": None,
    }
    final = get_graph().invoke(initial)
    return IncidentReport(**final["report"])
