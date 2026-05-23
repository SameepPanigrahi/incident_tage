# 🔍 AI Incident Root Cause Assistant

> Multi-agent LLM system for automated incident triage, root cause analysis,
> anomaly correlation, and remediation recommendation.

**Built for:** T-Mobile Senior AI Engineer Evaluation
**Author:** Sameep Panigrahi
**Date:** May 2026

---

## Architecture

```
 ┌──────────────┐    HTTP     ┌────────────────────────────────────────────┐
 │  Streamlit   │───────────►│            FastAPI Backend                 │
 │  Frontend    │◄───────────│  PII Masker │ Audit Logger │ API Router   │
 │  :8501       │   JSON     │                                            │
 └──────────────┘            │  ┌────────────────────────────────────┐    │
                             │  │    LangGraph Sequential Pipeline    │    │
                             │  │                                    │    │
                             │  │  Log Parser ──► Root Cause ──►     │    │
                             │  │  Correlation ──► Remediation ──►   │    │
                             │  │  Synthesizer ──► END               │    │
                             │  └──────────┬─────────────────────────┘    │
                             │             │                              │
                             │  ┌──────────▼─────────────────────────┐    │
                             │  │   RAG Pipeline (ChromaDB + OpenAI) │    │
                             │  │   Runbooks │ Past Incidents │ Logs │    │
                             │  └────────────────────────────────────┘    │
                             └────────────────────────────────────────────┘
```

## Quick Start

### Option 1: Docker Compose (recommended)
```bash
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

docker-compose up --build
```
- Backend API: http://localhost:8000
- Frontend UI: http://localhost:8501
- API docs: http://localhost:8000/docs

### Option 2: Manual Setup
```bash
python -m venv venv
source venv/bin/activate  # or venv\\Scripts\\activate on Windows
pip install -r requirements.txt

# Download spaCy model for PII detection
python -m spacy download en_core_web_lg

# Copy and configure .env
cp .env.example .env
# Add your OPENAI_API_KEY to .env

# Start the backend
uvicorn src.main:app --reload --port 8000

# In a separate terminal, start the frontend
streamlit run src/frontend/app.py
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/analyze` | Submit logs for full multi-agent analysis |
| POST | `/api/v1/ingest` | Re-ingest mock data into vector store |
| GET | `/api/v1/health` | Health check with vector store status |
| GET | `/api/v1/incidents/{id}` | Retrieve stored analysis (placeholder) |

### Example Request
```bash
curl -X POST http://localhost:8000/api/v1/analyze \\
  -H "Content-Type: application/json" \\
  -d '{
    "incident_id": "INC-2026-042",
    "logs": "<paste raw logs here>",
    "additional_context": "Deployment 30 mins before outage"
  }'
```

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Orchestration | LangGraph | State machines with conditional routing |
| Vector DB | ChromaDB | Zero-config MVP (prod: Azure AI Search) |
| LLM | GPT-4o-mini | 90% quality at 10% cost |
| Chunking | Log-aware + semantic | Respects log entry boundaries |
| PII | Presidio + regex fallback | Defence-in-depth |
| Logging | structlog → JSONL | Audit-compliant structured logs |

## Evaluation

Run the RAG evaluation:
```bash
python -m evaluation.eval_rag
```

Run unit tests:
```bash
pytest tests/ -v
```

## Future Improvements
- [ ] Slack/Teams integration for real-time incident alerts
- [ ] Multi-tenant support with RBAC
- [ ] Streaming responses via WebSocket
- [ ] Integration with PagerDuty / ServiceNow / Jira
- [ ] Fine-tuned embedding model on internal incident data
- [ ] Feedback loop for continuous RAG quality improvement
- [ ] Parallel agent execution (correlation + remediation)
- [ ] Prometheus metrics endpoint for pipeline observability
