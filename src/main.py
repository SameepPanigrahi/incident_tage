from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.config import get_settings, Settings
from src.models.schemas import IncidentAnalysisRequest, IncidentAnalysisResponse
from src.agents.graph import build_graph
from src.rag.ingestion import IncidentDataIngester
from src.security.pii_masking import PIIMasker
from src.security.audit_logger import AuditLogger
from langchain.callbacks.manager import tracing_v2_enabled

logger = logging.getLogger(__name__)

# ── Global singletons (set during lifespan) ──
_graph = None
_retriever = None
_vector_store = None
_pii_masker = PIIMasker()
_audit = AuditLogger()



import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),                              # Console
        logging.FileHandler("app.log", encoding="utf-8"),     # File
    ],
)

# import os
# print("LangSmith tracing:", os.getenv("LANGCHAIN_TRACING_V2"))
# print("LangSmith API key:", os.getenv("LANGCHAIN_API_KEY"))
# print("LangSmith project:", os.getenv("LANGCHAIN_PROJECT"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: build graph, ingest mock data if the collection is empty."""
    global _graph, _retriever, _vector_store

    settings = get_settings()
    _graph, _retriever, _vector_store = build_graph(settings)

    # Ingest mock data if collection is empty
    health = _vector_store.health_check()
    if health["document_count"] == 0:
        logger.info("Empty collection — ingesting mock data from %s", settings.MOCK_DATA_DIR)
        ingester = IncidentDataIngester(_vector_store, settings)
        counts = ingester.ingest_all(settings.MOCK_DATA_DIR)
        logger.info("Ingestion counts: %s", counts)
    else:
        logger.info(
            "Collection already has %d documents — skipping ingestion.",
            health["document_count"],
        )
    yield


app = FastAPI(
    title="AI Incident Root Cause Assistant",
    version="1.0.0",
    description="Multi-agent LLM system for automated incident triage and RCA.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Endpoints ────────────────────────────────────────────────────

@app.post("/api/v1/analyze", response_model=IncidentAnalysisResponse)
async def analyze_incident(request: IncidentAnalysisRequest):
    """Run the full multi-agent analysis pipeline on the submitted logs."""
    if _graph is None:
        raise HTTPException(status_code=503, detail="Pipeline not ready.")

    # Audit log
    _audit.log_query(request.incident_id, request.logs)

    # PII masking on input
    masked_logs = _pii_masker.mask(request.logs)
    masked_context = _pii_masker.mask(request.additional_context or "")

    # Build initial state
    initial_state: dict[str, Any] = {
        "incident_id": request.incident_id,
        "raw_logs": masked_logs,
        "additional_context": masked_context,
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
    try:
        # final_state = _graph.invoke(initial_state)
        with tracing_v2_enabled():
            final_state = _graph.invoke(initial_state)

    except Exception as exc:
        logger.exception("Pipeline failed for %s", request.incident_id)
        raise HTTPException(status_code=500, detail=str(exc))

    elapsed = round(time.time() - start, 2)

    # Build response
    summary_data = final_state.get("incident_summary", {})
    summary_data.setdefault("title", "Incident Analysis")
    summary_data.setdefault("severity", "medium")
    summary_data.setdefault("impacted_services", final_state.get("impacted_services", []))
    summary_data.setdefault("timeline", final_state.get("key_timestamps", []))
    summary_data.setdefault("summary", "Analysis complete.")
    summary_data.setdefault("key_events", final_state.get("error_patterns", []))

    response = IncidentAnalysisResponse(
        incident_id=request.incident_id,
        summary=summary_data,
        root_causes=final_state.get("root_causes", []),
        correlated_anomalies=final_state.get("correlated_anomalies", []),
        remediation_steps=final_state.get("remediation_steps", []),
        analysis_timestamp=datetime.now(timezone.utc).isoformat(),
        processing_time_seconds=elapsed,
    )

    _audit.log_analysis_complete(
        request.incident_id,
        len(response.root_causes),
        elapsed,
    )
    return response


@app.post("/api/v1/ingest")
async def ingest_data():
    """Re-ingest mock data into the vector store (resets collection)."""
    if _vector_store is None:
        raise HTTPException(status_code=503, detail="Vector store not ready.")

    settings = get_settings()
    _vector_store.reset_collection()
    ingester = IncidentDataIngester(_vector_store, settings)
    counts = ingester.ingest_all(settings.MOCK_DATA_DIR)
    return {"status": "ok", "ingested": counts}


@app.get("/api/v1/health")
async def health_check():
    """Return vector store health and pipeline readiness."""
    if _vector_store is None:
        return {"status": "initialising", "pipeline_ready": False}
    info = _vector_store.health_check()
    info["pipeline_ready"] = _graph is not None
    return info


@app.get("/api/v1/incidents/{incident_id}")
async def get_incident(incident_id: str):
    """Placeholder — in production this would fetch from a results store."""
    return {
        "incident_id": incident_id,
        "message": "Stored result retrieval not yet implemented. "
                   "Use POST /api/v1/analyze to run a new analysis.",
    }


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=True,
    )
