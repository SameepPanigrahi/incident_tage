from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from src.agents.state import IncidentState
from src.agents.log_parser import parse_logs
from src.agents.root_cause import analyze_root_cause
from src.agents.correlation import correlate_anomalies
from src.agents.remediation import recommend_remediation
from src.config import Settings, get_settings
from src.rag.retriever import IncidentRetriever
from src.rag.vector_store import ChromaVectorStore
import httpx
http_client = httpx.Client(verify=False)

logger = logging.getLogger(__name__)


def build_graph(settings: Settings | None = None):
    """Construct and compile the LangGraph incident-analysis pipeline.

    Returns:
        compiled_graph  — call ``compiled_graph.invoke(state)`` to run.
        retriever       — the IncidentRetriever instance (for health checks).
    """
    settings = settings or get_settings()

    # ── Shared resources ──
    llm = ChatOpenAI(
        model=settings.LLM_MODEL,
        openai_api_key=settings.OPENAI_API_KEY,
        temperature=0.1,   # Low temperature for deterministic analysis
        max_tokens=4096,
        http_client=http_client
    )
    vector_store = ChromaVectorStore(settings)
    retriever = IncidentRetriever(vector_store, settings)

    # ── Node wrappers (close over shared resources) ──

    def node_log_parser(state: dict[str, Any]) -> dict[str, Any]:
        return parse_logs(state, llm)

    def node_root_cause(state: dict[str, Any]) -> dict[str, Any]:
        return analyze_root_cause(state, llm, retriever)

    def node_correlation(state: dict[str, Any]) -> dict[str, Any]:
        return correlate_anomalies(state, llm)

    def node_remediation(state: dict[str, Any]) -> dict[str, Any]:
        return recommend_remediation(state, llm, retriever)

    def node_synthesizer(state: dict[str, Any]) -> dict[str, Any]:
        """Final node — assembles all agent outputs into a summary.

        If the root_cause agent already produced an incident_summary we
        reuse it; otherwise we build one from available data.
        """
        summary = state.get("incident_summary", {})
        if not summary:
            summary = {
                "title": "Incident Analysis",
                "severity": "medium",
                "summary": "Analysis completed — see root causes and remediation.",
                "impacted_services": state.get("impacted_services", []),
                "timeline": state.get("key_timestamps", []),
                "key_events": state.get("error_patterns", []),
            }
        else:
            # Ensure all expected keys are present
            summary.setdefault("impacted_services", state.get("impacted_services", []))
            summary.setdefault("timeline", state.get("key_timestamps", []))
            summary.setdefault("key_events", state.get("error_patterns", []))
        return {"incident_summary": summary}

    # ── Router ──
    def should_continue(state: dict[str, Any]) -> str:
        """Route after log parsing: continue only if entries were extracted."""
        if state.get("parsed_entries"):
            return "continue"
        logger.warning("Log parsing produced no entries — skipping analysis.")
        return "abort"

    # ── Build graph ──
    workflow = StateGraph(IncidentState)

    workflow.add_node("log_parser", node_log_parser)
    workflow.add_node("root_cause_analyzer", node_root_cause)
    workflow.add_node("correlation_engine", node_correlation)
    workflow.add_node("remediation_agent", node_remediation)
    workflow.add_node("synthesizer", node_synthesizer)

    # Edges
    workflow.set_entry_point("log_parser")
    workflow.add_conditional_edges(
        "log_parser",
        should_continue,
        {
            "continue": "root_cause_analyzer",
            "abort": END,
        },
    )
    workflow.add_edge("root_cause_analyzer", "correlation_engine")
    workflow.add_edge("correlation_engine", "remediation_agent")
    workflow.add_edge("remediation_agent", "synthesizer")
    workflow.add_edge("synthesizer", END)

    compiled = workflow.compile()
    logger.info("LangGraph incident pipeline compiled successfully.")
    return compiled, retriever, vector_store


async def run_analysis(
    incident_id: str,
    logs: str,
    additional_context: str = "",
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Convenience wrapper: build graph, invoke, return response dict."""
    settings = settings or get_settings()
    graph, _, _ = build_graph(settings)

    initial_state: dict[str, Any] = {
        "incident_id": incident_id,
        "raw_logs": logs,
        "additional_context": additional_context,
        "parsed_entries": [],
        "impacted_services": [],
        "key_timestamps": [],
        "error_patterns": [],
        "incident_summary": {},
        "root_causes": [],
        "retrieved_runbook_context": "",
        "correlated_anomalies": [],
        "remediation_steps": [],
        "retrieved_remediation_context": "",
        "messages": [],
    }

    start = time.time()
    final_state = graph.invoke(initial_state)
    elapsed = round(time.time() - start, 2)

    return {
        "incident_id": incident_id,
        "summary": final_state.get("incident_summary", {}),
        "root_causes": final_state.get("root_causes", []),
        "correlated_anomalies": final_state.get("correlated_anomalies", []),
        "remediation_steps": final_state.get("remediation_steps", []),
        "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
        "processing_time_seconds": elapsed,
    }
