from __future__ import annotations

import logging
import sys
from pathlib import Path

import structlog


class AuditLogger:
    """Structured audit logger that writes to console AND a JSONL file.

    Usage::

        audit = AuditLogger()
        audit.log_query(incident_id="INC-001", query_text="logs from auth-service")
    """

    def __init__(
        self,
        log_file: str = "audit_trail.jsonl",
        log_level: str = "INFO",
    ) -> None:
        # Ensure the log file directory exists
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)

        # Configure structlog
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(
                logging.getLevelName(log_level.upper())
            ),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )

        self._log = structlog.get_logger("audit")
        self._log_file = log_file

    def _persist(self, event_dict: dict) -> None:
        """Append a JSON line to the audit trail file."""
        import json
        with open(self._log_file, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event_dict) + "\n")

    # ── Event methods ────────────────────────────────────────────

    def log_query(
        self,
        incident_id: str,
        query_text: str,
        user_id: str = "system",
    ) -> None:
        """Log an incoming analysis request."""
        event = {
            "event": "query_received",
            "incident_id": incident_id,
            "query_length": len(query_text),
            "user_id": user_id,
        }
        self._log.info(**event)
        self._persist(event)

    def log_retrieval(
        self,
        incident_id: str,
        num_docs_retrieved: int,
        sources: list[str],
    ) -> None:
        """Log a RAG retrieval event."""
        event = {
            "event": "rag_retrieval",
            "incident_id": incident_id,
            "num_docs": num_docs_retrieved,
            "sources": sources,
        }
        self._log.info(**event)
        self._persist(event)

    def log_analysis_complete(
        self,
        incident_id: str,
        root_causes_found: int,
        processing_time: float,
    ) -> None:
        """Log completion of the analysis pipeline."""
        event = {
            "event": "analysis_complete",
            "incident_id": incident_id,
            "root_causes_found": root_causes_found,
            "processing_time_seconds": processing_time,
        }
        self._log.info(**event)
        self._persist(event)

    def log_security_event(
        self,
        event_type: str,
        details: dict,
    ) -> None:
        """Log a security-related event (PII detection, access, etc.)."""
        event = {
            "event": "security",
            "security_event_type": event_type,
            **details,
        }
        self._log.warning(**event)
        self._persist(event)
