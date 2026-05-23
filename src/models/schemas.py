from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────

class SeverityLevel(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RootCauseCategory(str, Enum):
    MEMORY_LEAK = "memory_leak"
    DB_CONNECTION_EXHAUSTION = "db_connection_exhaustion"
    DEPLOYMENT_FAILURE = "deployment_failure"
    API_TIMEOUT_PROPAGATION = "api_timeout_propagation"
    MISCONFIGURATION = "misconfiguration"
    NETWORK_ISSUE = "network_issue"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    UNKNOWN = "unknown"


# ── Internal Models ───────────────────────────────────────────────

class ParsedLogEntry(BaseModel):
    """A single parsed log line."""
    timestamp: str
    service: str
    level: str  # INFO, WARN, ERROR, FATAL
    message: str
    error_code: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class IncidentSummary(BaseModel):
    """High-level incident summary produced by the synthesizer."""
    title: str
    severity: SeverityLevel
    impacted_services: list[str]
    timeline: list[dict[str, str]]  # [{"timestamp": "...", "event": "..."}]
    summary: str
    key_events: list[str]


class RootCause(BaseModel):
    """A single identified root cause with supporting evidence."""
    cause: str
    confidence: ConfidenceLevel
    reasoning: str
    evidence: list[str]
    category: RootCauseCategory


class CorrelatedAnomaly(BaseModel):
    """An anomaly correlated to the incident across services."""
    service: str
    anomaly_type: str
    timestamp: str
    correlation_score: float = Field(ge=0.0, le=1.0)
    description: str


class Remediation(BaseModel):
    """A single prioritized remediation step."""
    step: int
    action: str
    priority: str  # "immediate", "short-term", "long-term"
    estimated_impact: str
    source_document: Optional[str] = None


# ── API Request / Response ────────────────────────────────────────

class IncidentAnalysisRequest(BaseModel):
    """Incoming request to analyze an incident."""
    incident_id: str = Field(..., examples=["INC-2026-042"])
    logs: str = Field(..., description="Raw log text to analyze")
    additional_context: Optional[str] = Field(
        None, description="Optional extra context (e.g. recent deployments)"
    )


class IncidentAnalysisResponse(BaseModel):
    """Full analysis response returned to the caller."""
    incident_id: str
    summary: IncidentSummary
    root_causes: list[RootCause]
    correlated_anomalies: list[CorrelatedAnomaly]
    remediation_steps: list[Remediation]
    analysis_timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat()
    )
    processing_time_seconds: float
