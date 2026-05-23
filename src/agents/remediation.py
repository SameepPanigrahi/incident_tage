from __future__ import annotations

import json
import logging
from typing import Any

from langchain_openai import ChatOpenAI

from src.rag.retriever import IncidentRetriever

logger = logging.getLogger(__name__)

REMEDIATION_SYSTEM_PROMPT = """You are an incident commander drafting a remediation plan for an active
production incident.

Given:
- Identified root causes with confidence and evidence.
- Retrieved runbook / SOP procedures from the organisation's knowledge base.

Your task:
1. Generate a PRIORITISED list of remediation steps.
2. Each step MUST include:
   * step: sequential number.
   * action: clear, actionable instruction (include specific commands
     if found in the runbooks).
   * priority: "immediate" (do now), "short-term" (within 24h),
     or "long-term" (within 1-2 weeks).
   * estimated_impact: what this step fixes or prevents.
   * source_document: name of the runbook/SOP this came from,
     or null if based on general expertise.
3. Order: immediate steps first, then short-term, then long-term.
4. Include BOTH reactive fixes AND preventive measures.

Respond with a JSON object:
{
  "remediation_steps": [
    {
      "step": 1,
      "action": "Increase DB connection pool max_size from 20 to 50...",
      "priority": "immediate",
      "estimated_impact": "Restores DB connectivity for auth-service",
      "source_document": "database_troubleshooting.md"
    }
  ]
}
"""


def recommend_remediation(
    state: dict[str, Any],
    llm: ChatOpenAI,
    retriever: IncidentRetriever,
) -> dict[str, Any]:
    """LangGraph node: generate prioritised remediation steps.

    1. Retrieves remediation-specific runbook context via RAG.
    2. Passes root causes + context to the LLM.
    3. Returns ordered remediation steps.
    """
    root_causes = state.get("root_causes", [])

    # ── RAG retrieval ──
    context, sources = retriever.retrieve_for_remediation(root_causes)
    logger.info("Remediation Agent retrieved context from: %s", sources)

    user_msg_parts = [
        "IDENTIFIED ROOT CAUSES:",
        json.dumps(root_causes, indent=2),
        "",
        "RETRIEVED RUNBOOK / SOP CONTEXT:",
        context,
    ]
    user_msg = "\n".join(user_msg_parts)

    response = llm.invoke(
        [
            {"role": "system", "content": REMEDIATION_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
    )

    try:
        parsed = json.loads(response.content)
    except json.JSONDecodeError:
        logger.error("Remediation Agent returned invalid JSON.")
        parsed = {}

    steps = parsed.get("remediation_steps", [])
    logger.info("Remediation Agent -> %d steps generated", len(steps))
    return {
        "remediation_steps": steps,
        "retrieved_remediation_context": context,
    }
