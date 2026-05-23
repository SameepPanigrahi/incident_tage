from __future__ import annotations

from typing import Annotated, Any
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class IncidentState(TypedDict):
    """Shared state flowing through the LangGraph pipeline.

    Each agent reads what it needs and writes its outputs.
    The ``messages`` key uses LangGraph's built-in message
    accumulator so chat history is preserved automatically.
    """

    # ── Input ──
    incident_id: str
    raw_logs: str
    additional_context: str

    # ── Log Parser outputs ──
    parsed_entries: list[dict[str, Any]]       # List of parsed log entries
    impacted_services: list[str]               # Unique services affected
    key_timestamps: list[dict[str, str]]       # [{"label": ..., "timestamp": ...}]
    error_patterns: list[str]                  # Recurring error signatures

    # ── Root Cause Analyzer outputs ──
    incident_summary: dict[str, Any]           # IncidentSummary as dict
    root_causes: list[dict[str, Any]]          # List of RootCause dicts
    retrieved_runbook_context: str              # RAG context used

    # ── Correlation Engine outputs ──
    correlated_anomalies: list[dict[str, Any]] # CorrelatedAnomaly dicts

    # ── Remediation Agent outputs ──
    remediation_steps: list[dict[str, Any]]    # Remediation dicts
    retrieved_remediation_context: str          # RAG context used

    # ── LangGraph message history ──
    messages: Annotated[list, add_messages]
