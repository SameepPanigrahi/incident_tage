from __future__ import annotations

import json
import logging
from typing import Any

from langchain_openai import ChatOpenAI

from src.rag.retriever import IncidentRetriever

logger = logging.getLogger(__name__)

ROOT_CAUSE_SYSTEM_PROMPT = """You are a Principal SRE performing root-cause analysis on a production
incident. You have access to:
1. Parsed log entries and error patterns from the current incident.
2. Retrieved knowledge from internal runbooks and past incident reports.

INSTRUCTIONS:
- Identify 1-3 probable root causes, ranked by confidence.
- For each root cause provide:
  * cause: A concise description (one sentence).
  * confidence: "high", "medium", or "low".
  * reasoning: A detailed chain-of-thought explaining how you arrived
    at this conclusion (2-4 sentences).
  * evidence: List of specific log entries or patterns that support it.
  * category: One of memory_leak | db_connection_exhaustion |
    deployment_failure | api_timeout_propagation | misconfiguration |
    network_issue | resource_exhaustion | unknown.

IMPORTANT:
- Ground your analysis in the LOG EVIDENCE, not speculation.
- Cross-reference with the retrieved context from runbooks/past incidents.
- If a past incident matches the current pattern, reference it explicitly.

Respond with a JSON object:
{
  "incident_summary": {
    "title": "...",
    "severity": "critical|high|medium|low",
    "summary": "One-paragraph summary of the incident."
  },
  "root_causes": [
    {
      "cause": "...",
      "confidence": "high",
      "reasoning": "...",
      "evidence": ["log line 1", "error pattern X"],
      "category": "db_connection_exhaustion"
    }
  ]
}
"""


def analyze_root_cause(
    state: dict[str, Any],
    llm: ChatOpenAI,
    retriever: IncidentRetriever,
) -> dict[str, Any]:
    """LangGraph node: determine probable root causes.

    1. Retrieves relevant runbook & past-incident context via RAG.
    2. Passes parsed data + context to the LLM.
    3. Returns root causes and an incident summary.
    """
    error_patterns = state.get("error_patterns", [])
    services = state.get("impacted_services", [])
    parsed_entries = state.get("parsed_entries", [])

    # ── RAG retrieval ──
    context, sources = retriever.retrieve_for_root_cause(error_patterns, services)
    logger.info("Root Cause Analyzer retrieved context from: %s", sources)

    # ── Build user message ──
    user_msg_parts = [
        "PARSED LOG ENTRIES (sample - up to 30):",
        json.dumps(parsed_entries[:30], indent=2),
        "",
        f"IMPACTED SERVICES: {', '.join(services)}",
        "",
        "ERROR PATTERNS:",
        *[f"  - {p}" for p in error_patterns],
        "",
        "RETRIEVED KNOWLEDGE BASE CONTEXT:",
        context,
    ]
    user_msg = "\n".join(user_msg_parts)

    response = llm.invoke(
        [
            {"role": "system", "content": ROOT_CAUSE_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
    )

    try:
        parsed = json.loads(response.content)
    except json.JSONDecodeError:
        logger.error("Root Cause Analyzer returned invalid JSON.")
        parsed = {}

    result = {
        "incident_summary": parsed.get("incident_summary", {}),
        "root_causes": parsed.get("root_causes", []),
        "retrieved_runbook_context": context,
    }
    logger.info(
        "Root Cause Analyzer -> %d causes identified",
        len(result["root_causes"]),
    )
    return result
