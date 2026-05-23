from __future__ import annotations

import json
import logging
from typing import Any

from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

LOG_PARSER_SYSTEM_PROMPT = """You are a senior Site Reliability Engineer specialised in log analysis.
Your task is to parse the raw log text provided and extract structured information.

INSTRUCTIONS:
1. Parse each log line into a structured entry with: timestamp, service, level, message, error_code (if present).
2. Identify ALL unique services mentioned in the logs.
3. Extract key timestamps:
   - "first_error": timestamp of the very first ERROR/FATAL entry
   - "escalation": when the issue clearly worsened (e.g. more services affected, higher severity)
   - "peak_impact": when the most services were affected simultaneously
   - "last_entry": final log timestamp
4. Identify recurring error patterns (error codes, repeated messages, exception types).

Handle edge cases:
- If a line has no timestamp, associate it with the previous entry (e.g. stack traces).
- Mixed log formats are acceptable — do your best.
- If the log data is empty or unintelligible, return empty lists.

Respond with a JSON object matching EXACTLY this schema:
{
  "parsed_entries": [
    {
      "timestamp": "2024-01-15T10:30:45Z",
      "service": "auth-service",
      "level": "ERROR",
      "message": "Failed to acquire DB connection",
      "error_code": "DB_POOL_EXHAUSTED"
    }
  ],
  "impacted_services": ["auth-service", "api-gateway"],
  "key_timestamps": [
    {"label": "first_error", "timestamp": "2024-01-15T10:30:45Z"},
    {"label": "peak_impact", "timestamp": "2024-01-15T10:45:00Z"}
  ],
  "error_patterns": [
    "DB_POOL_EXHAUSTED repeated 12 times in auth-service",
    "Connection timeout to postgres:5432"
  ]
}
"""


def parse_logs(state: dict[str, Any], llm: ChatOpenAI) -> dict[str, Any]:
    """LangGraph node: parse raw logs into structured data.

    Args:
        state: Current graph state (must contain ``raw_logs``).
        llm:   ChatOpenAI instance.

    Returns:
        Dict with keys ``parsed_entries``, ``impacted_services``,
        ``key_timestamps``, ``error_patterns``.
    """
    raw_logs = state.get("raw_logs", "")
    additional = state.get("additional_context", "")

    if not raw_logs.strip():
        logger.warning("Log Parser received empty logs.")
        return {
            "parsed_entries": [],
            "impacted_services": [],
            "key_timestamps": [],
            "error_patterns": [],
        }

    user_msg = f"RAW LOGS:\n{raw_logs}"
    if additional:
        user_msg += f"\n\nADDITIONAL CONTEXT:\n{additional}"

    response = llm.invoke(
        [
            {"role": "system", "content": LOG_PARSER_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
    )

    try:
        parsed = json.loads(response.content)
    except json.JSONDecodeError:
        logger.error("Log Parser LLM returned invalid JSON.")
        parsed = {}

    result = {
        "parsed_entries": parsed.get("parsed_entries", []),
        "impacted_services": parsed.get("impacted_services", []),
        "key_timestamps": parsed.get("key_timestamps", []),
        "error_patterns": parsed.get("error_patterns", []),
    }
    logger.info(
        "Log Parser -> %d entries, %d services, %d patterns",
        len(result["parsed_entries"]),
        len(result["impacted_services"]),
        len(result["error_patterns"]),
    )
    return result
