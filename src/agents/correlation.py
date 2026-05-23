from __future__ import annotations

import json
import logging
from typing import Any

from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

CORRELATION_SYSTEM_PROMPT = """You are a distributed systems expert analysing cross-service anomaly
correlations during a production incident.

Given:
- Parsed log entries from multiple services
- Identified root causes
- Key timestamps

Your task:
1. Identify anomalies that are TEMPORALLY CORRELATED across different
   services (events that happened within +/-5 minutes of each other and
   are likely related).
2. Detect CASCADING FAILURE patterns — where failure in Service A
   caused downstream failures in Service B, C, etc.
3. Score each correlation from 0.0 (unlikely) to 1.0 (certain).
4. Describe the causal chain.

Respond with a JSON object:
{
  "correlated_anomalies": [
    {
      "service": "api-gateway",
      "anomaly_type": "cascading_timeout",
      "timestamp": "2024-01-15T10:35:00Z",
      "correlation_score": 0.92,
      "description": "API gateway began returning 503s 5 minutes after auth-service failed, consistent with dependency timeout propagation."
    }
  ]
}
"""


def correlate_anomalies(
    state: dict[str, Any],
    llm: ChatOpenAI,
) -> dict[str, Any]:
    """LangGraph node: find correlated anomalies across services."""
    parsed_entries = state.get("parsed_entries", [])
    root_causes = state.get("root_causes", [])
    key_timestamps = state.get("key_timestamps", [])
    services = state.get("impacted_services", [])

    user_msg_parts = [
        "PARSED LOG ENTRIES (sample - up to 30):",
        json.dumps(parsed_entries[:30], indent=2),
        "",
        f"IMPACTED SERVICES: {', '.join(services)}",
        "",
        "KEY TIMESTAMPS:",
        json.dumps(key_timestamps, indent=2),
        "",
        "IDENTIFIED ROOT CAUSES:",
        json.dumps(root_causes, indent=2),
    ]
    user_msg = "\n".join(user_msg_parts)

    response = llm.invoke(
        [
            {"role": "system", "content": CORRELATION_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
    )

    try:
        parsed = json.loads(response.content)
    except json.JSONDecodeError:
        logger.error("Correlation Engine returned invalid JSON.")
        parsed = {}

    anomalies = parsed.get("correlated_anomalies", [])
    logger.info("Correlation Engine -> %d anomalies found", len(anomalies))
    return {"correlated_anomalies": anomalies}
