# 🤖 AI Incident Root Cause Assistant

> Multi-Agent LLM System for Automated Incident Triage, Root Cause Analysis, Anomaly Correlation & Remediation Recommendation

**Author:** Sameep Panigrahi  
**Role:** Senior Associate – Data Science  
**Date:** May 2026  
**Tech Stack:** LangGraph · GPT-4o-mini · ChromaDB · FastAPI · LangSmith · Streamlit

---

## 📋 Problem Statement

During production outages, engineers must manually read thousands of log lines, correlate timestamps across services, cross-reference runbooks, and search past incidents — taking **30–60 minutes per incident** with high error rates due to fatigue.

**Our Solution:** 4 specialized AI agents working in sequence deliver automated triage in **~70 seconds** — consistent, grounded in actual runbooks, and fully traceable via LangSmith.

---

## 🎯 Four Core Capabilities

| Capability | Description |
|---|---|
| 📝 **Incident Summarization** | Reads multi-service logs → generates structured summary with impacted services, timeline, and error patterns |
| 🎯 **Root Cause Detection** | Analyzes error patterns with RAG context from runbooks + past incidents → returns 1–3 ranked causes with confidence scores, evidence, and reasoning |
| 🔗 **Anomaly Correlation** | Finds cross-service cascading failures with temporal analysis → scores each correlation 0.0–1.0 |
| 🛠️ **Remediation Recommendations** | Retrieves fix procedures from runbooks via RAG → prioritized: immediate → short-term → long-term with actual commands & source citations |

---

## 🏗️ System Architecture

```
┌──────────────┐  HTTP   ┌──────────────────────────────────────────────────────┐
│  Streamlit   │────────►│                  FastAPI Backend                     │
│  Frontend    │◄────────│  PII Masker (Presidio + Regex)  │  Audit Logger      │
│  :8501       │  JSON   │                                                      │
└──────────────┘         │  ┌──────────────────────────────────────────────┐    │
                         │  │       LangGraph Sequential Pipeline          │    │
                         │  │                                              │    │
                         │  │  START → Log Parser → Router →               │    │
                         │  │  Root Cause Analyzer (RAG) →                 │    │
                         │  │  Correlation Engine →                        │    │
                         │  │  Remediation Agent (RAG) →                   │    │
                         │  │  Synthesizer → END                           │    │
                         │  └──────────────┬───────────────────────────────┘    │
                         │                 │                                     │
                         │  ┌──────────────▼───────────────────────────────┐    │
                         │  │     ChromaDB Vector Store (Persistent)       │    │
                         │  │     Runbooks (.md)  │  Past Incidents (.json)│    │
                         │  │     ⚠️ Logs are NOT ingested — sent          │    │
                         │  │        directly to Agent 1 (Log Parser)      │    │
                         │  └──────────────────────────────────────────────┘    │
                         │                                                      │
                         │  ┌──────────────────────────────────────────────┐    │
                         │  │         LangSmith Observability              │    │
                         │  │  Full trace tree │ Evaluation metrics        │    │
                         │  │  Token tracking  │ Feedback scoring          │    │
                         │  └──────────────────────────────────────────────┘    │
                         └──────────────────────────────────────────────────────┘
```

**Key Design Principles:**
- **Sequential pipeline:** START → Parser → Router → Root Cause → Correlation → Remediation → Synthesizer → END
- **Shared TypedDict state:** Each agent reads from and writes to a common state dictionary
- **Auto-ingestion at startup:** ChromaDB populated on first boot via FastAPI lifespan event
- **Conditional routing:** Router skips remaining agents if log parsing produces nothing
- **Purposeful data ingestion:** Only runbooks + past incidents are ingested — logs go directly to Agent 1

---

## 🔄 The 4 Agents

### Agent 1: Log Parser
- **Input:** Raw multi-service log text (user-pasted)
- **Model:** GPT-4o-mini with JSON mode (structured output)
- **Output:** `parsed_entries`, `impacted_services`, `key_timestamps`, `error_patterns`
- **Edge Cases:** Empty/malformed logs → Router skips remaining agents

### Agent 2: Root Cause Analyzer (RAG-Augmented)
- **RAG Retrieval:** Searches ChromaDB for runbooks (`doc_type='runbook'`) + past incidents (`doc_type='past_incident'`) — top 3 each
- **Output:** 1–3 ranked root causes with `category`, `confidence`, `reasoning`, `evidence`
- **Categories:** `db_connection_exhaustion`, `memory_leak`, `api_timeout_propagation`, etc.

### Agent 3: Correlation Engine
- **Process:** Pure LLM analysis (NO RAG — analytical, not retrieval)
- **Detects:** Cascading failure chains, temporal patterns, circuit breaker propagation
- **Output:** Per anomaly: `service`, `anomaly_type`, `timestamp`, `correlation_score` (0.0–1.0), `description`

### Agent 4: Remediation Agent (RAG-Augmented)
- **RAG Retrieval:** Searches runbooks ONLY (`doc_type='runbook'`) — top 5
- **Output:** Prioritized fix steps with `priority` (immediate/short-term/long-term), `action`, `impact`, `source_document`
- **Grounding:** Every step cites which runbook it came from — proves RAG grounding, not hallucination

---

## ⚙️ Technology Stack

| Component | Technology | Why This Choice |
|---|---|---|
| Backend API | FastAPI | Async support, automatic OpenAPI docs, Pydantic validation |
| Agent Orchestration | LangGraph | State machines with conditional routing, TypedDict state |
| Vector Database | ChromaDB (persistent) | Zero-config, metadata filtering (`doc_type`), persistent on disk |
| LLM | GPT-4o-mini (temp=0.1) | 90% of GPT-4o quality at 10% cost. Low temp for consistent JSON |
| Embeddings | text-embedding-3-small | 1536 dimensions, optimized for retrieval, cost-effective |
| Frontend | Streamlit | Rapid prototyping, interactive UI, built-in session state |
| PII Protection | Presidio + regex fallback | Defence-in-depth: NER-based + pattern-based |
| Observability | LangSmith | Full trace tree, evaluation metric scoring, experiment tracking |
| Evaluation | Custom deterministic metrics | Free, instant, CI/CD friendly, 25+ domain-specific metrics |

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- OpenAI API key
- (Optional) LangSmith API key for tracing

### Setup & Run

```bash
# Clone the repository
git clone https://github.com/SameepPanigrahi/incident_tage.git
cd incident_tage

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Download spaCy model for PII detection
python -m spacy download en_core_web_lg

# Configure environment variables
cp .env.example .env
# Edit .env and add your keys:
#   OPENAI_API_KEY=sk-xxx
#   LANGCHAIN_TRACING_V2=true          (optional - for LangSmith tracing)
#   LANGCHAIN_API_KEY=lsv2_pt_xxx      (optional - for LangSmith tracing)
#   LANGCHAIN_PROJECT=incident-rca-assistant

# Start the backend
uvicorn src.main:app --reload --port 8000

# In a separate terminal, start the frontend
streamlit run src/frontend/app.py
```

**Access Points:**
- 🖥️ Frontend UI: http://localhost:8501
- 🔌 Backend API: http://localhost:8000
- 📄 API Docs (Swagger): http://localhost:8000/docs

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/analyze` | Submit logs for full multi-agent analysis |
| `POST` | `/api/v1/ingest` | Re-ingest mock data into vector store |
| `GET` | `/api/v1/health` | Health check with vector store status |
| `GET` | `/api/v1/incidents/{id}` | Retrieve stored analysis (placeholder) |

### Example Request

```bash
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "incident_id": "INC-2026-042",
    "logs": "<paste raw logs here>",
    "additional_context": "Deployment 30 mins before outage"
  }'
```

---

## 📚 RAG Pipeline — Knowledge Base

### What We Ingest (2 Sources)

**📄 Runbooks (.md) — 4 files** (Semantic chunking: 512 chars, 50 overlap)
- `database_troubleshooting.md`
- `memory_leak_diagnosis.md`
- `timeout_cascade_prevention.md`
- `deployment_rollback_sop.md`

**📋 Past Incidents (.json) — 3 files** (JSON flattened to text)
- `incident_001` — Auth service outage (June 2024)
- `incident_002` — Payment memory leak (Aug 2024)
- `incident_003` — Timeout cascade (Nov 2024)

### What We DON'T Ingest — Incident Logs
- User-pasted logs go **directly** to Agent 1 (Log Parser)
- No agent searches `doc_type='log'` from ChromaDB
- Keeps vector DB clean and retrieval precise

### Domain-Specific Retrieval
- `retrieve_for_root_cause()` → runbooks + past incidents
- `retrieve_for_remediation()` → runbooks ONLY
- Metadata filtering: `doc_type='runbook'` vs `'past_incident'`

### Auto-Ingestion
FastAPI lifespan checks ChromaDB → if `document_count == 0` → `IncidentDataIngester` reads `mock_data/` → chunks → embeds → stores. Subsequent startups skip ingestion. ~35 chunks total persisted in `chroma_db/`.

---

## 🔒 Security & Enterprise Readiness

### PII Masking (Defence-in-Depth)
| Layer | Method | What It Catches |
|---|---|---|
| Layer 1 | Microsoft Presidio (NER-based) | Names, organizations, locations via NLP |
| Layer 2 | Regex Fallback Patterns | Emails → `<EMAIL>`, IPs → `<IP_ADDRESS>`, SSNs, credit cards, phone numbers |

**Applied to:** Both input logs AND LLM output

### Logging (Two Separate Systems)
- **📋 Audit Logger** (`audit_trail.jsonl`) — Structured JSON per event (query_received, analysis_complete, security_event) → for compliance & auditors
- **📝 Application Logger** (`app.log` + console) — Python logging across all files → for engineers debugging

---

## ☁️ LangSmith Observability & Tracing

### Setup
```bash
# Add to .env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_pt_xxx
LANGCHAIN_PROJECT=incident-rca-assistant
```

### What's Traced Per Request
Full trace tree visible in LangSmith dashboard:
```
├── log_parser            4.2s   3,340 tokens
├── root_cause_analyzer   6.1s   4,750 tokens
│   └── ChromaDB retrieval  0.3s   6 docs
├── correlation_engine    3.8s   3,200 tokens
├── remediation_agent     5.5s   4,100 tokens
│   └── ChromaDB retrieval  0.2s   5 docs
└── synthesizer           0.1s
Total: ~70s | ~15,000 tokens | ~$0.008
```

Evaluation metrics are also logged as **feedback scores** in LangSmith — visible in Runs tab → Feedback columns.

---

## 🧪 Evaluation Strategy — 3 Levels, 25+ Metrics

| Level | File | What It Tests | Test Cases | Cost | Our Score |
|---|---|---|---|---|---|
| Level 1: Retrieval | `eval_rag.py` | ChromaDB returns right documents? | 10 queries | $0 (free) | **100% hit rate** |
| Level 2: Agent-Level | `eval_agents.py` | Each agent produces correct output? | 12 (3×4 agents) | ~$0.05 | **100% (12/12)** |
| Level 3: End-to-End | `eval_end_to_end.py` | Full pipeline gives right answer? | 3 scenarios ×16 checks | ~$0.05 | **92% (44/48)** |

### Run Evaluations

```bash
# Run all 3 levels at once (master runner)
python -m evaluation.run_all_evals

# Run individual levels
python -m evaluation.eval_rag
python -m evaluation.eval_agents
python -m evaluation.eval_end_to_end
```

All metrics are logged to **LangSmith as scored feedback** and saved locally to `evaluation/results/` as JSON.

---

### 📊 Level 1 — Retrieval Metrics (3 Metrics)

| Metric | What It Measures | Our Score |
|---|---|---|
| **Hit Rate** | Did at least 1 retrieved doc come from expected source? | 100% (10/10) |
| **Precision@K** | Of K retrieved docs, how many were relevant? | 78% |
| **MRR** | How high is the first relevant doc in results? | 0.950 |

### 📊 Level 2 — Agent-Level Metrics (18 Metrics)

**Agent 1: Log Parser (4 metrics)**
| Metric | What It Measures | Our Score |
|---|---|---|
| Service F1 | Found all impacted services AND only real ones? | 1.00 |
| Timestamp Accuracy | Identified correct `first_error` timestamp? | ✅ All correct |
| Error Pattern Recall | Caught all recurring error patterns? (count ≥ 2) | 4–5 patterns |
| Entry Count | Parsed enough log entries? (count ≥ 10) | 31–38 entries |

**Agent 2: Root Cause Analyzer (5 metrics)**
| Metric | What It Measures | Our Score |
|---|---|---|
| Category Match | Identified correct root cause type? (enum check) | ✅ All 3 match |
| Confidence Match | HIGH confidence assigned to correct causes? | ✅ All high |
| Evidence Grounding | Each root cause cites actual log evidence? (≥1 item) | 3–4 items each |
| Reasoning Quality | Reasoning chain is substantial? (≥30 chars) | 303–377 chars |
| Keyword Coverage | Analysis mentions expected terms? (pool, exhausted, etc.) | 100% (3/3) |

**Agent 3: Correlation Engine (4 metrics)**
| Metric | What It Measures | Our Score |
|---|---|---|
| Anomaly Count | Found enough cross-service anomalies? (≥ min) | 4–5 found |
| Service Coverage | Anomalies span all expected impacted services? | 100% |
| Score Validity | All correlation scores between 0.0 and 1.0? | ✅ All valid |
| Description Quality | Each anomaly has meaningful description? (>20 chars) | ✅ All have |

**Agent 4: Remediation Agent (5 metrics)**
| Metric | What It Measures | Our Score |
|---|---|---|
| Step Count | Enough fix steps generated? (≥ 3) | 6–8 steps |
| Has Immediate Priority | At least one "do this NOW" step? | ✅ All have |
| Priority Ordering | Steps ordered: immediate → short-term → long-term? | ✅ All ordered |
| Source Citation | Steps cite which runbook they came from? | ✅ All cited |
| Keyword Coverage | Steps contain expected fix commands? | 67–100% |

### 📊 Level 3 — End-to-End Pipeline (16 Checks × 3 Scenarios)

| # | Check | Auth Outage | Payment Leak | API Timeout |
|---|---|---|---|---|
| 1 | services_count | ✅ | ✅ | ✅ |
| 2 | services_must_include | ✅ | ✅ | ✅ |
| 3 | root_cause_count | ✅ | ✅ | ✅ |
| 4 | root_cause_category | ✅ | ✅ | ✅ |
| 5 | root_cause_has_evidence | ✅ | ✅ | ✅ |
| 6 | root_cause_has_reasoning | ✅ | ✅ | ✅ |
| 7 | root_cause_keywords | ✅ | ✅ | ✅ |
| 8 | severity_match | ✅ | ✅ | ❌ |
| 9 | remediation_count | ✅ | ✅ | ✅ |
| 10 | has_immediate_step | ✅ | ✅ | ✅ |
| 11 | priority_ordering | ✅ | ✅ | ✅ |
| 12 | has_source_citation | ✅ | ✅ | ✅ |
| 13 | remediation_keywords | ✅ | ✅ | ✅ |
| 14 | anomaly_count | ✅ | ✅ | ✅ |
| 15 | scores_valid | ✅ | ✅ | ✅ |
| 16 | processing_time | ❌ (76s) | ❌ (87s) | ❌ (81s) |

**Results:** Auth Outage = 15/16 (94%) | Payment Leak = 15/16 (94%) | API Timeout = 14/16 (88%) | **Overall = 44/48 (92%)**

---

## 🤔 Why Deterministic Metrics Over RAGAS?

| Aspect | Our Deterministic Metrics | RAGAS (LLM-as-Judge) |
|---|---|---|
| Output Type | Designed for structured JSON (enums, arrays, scores) | Designed for free-text paragraph answers |
| Actionability | `category_match` failed → tells you EXACTLY what broke | `faithfulness=0.78` → nothing actionable |
| Cost | **$0** per evaluation run | ~$0.50 per run (20+ extra LLM calls) |
| Speed | **< 1 second** for all metrics | 2–3 minutes per run |
| Determinism | Same input = same score **EVERY** time | ±10% variance across runs |
| CI/CD Ready | ✅ Run on every commit | ❌ Too slow and expensive |

**Our Metrics Cover RAGAS Equivalents:**
- `MRR` ≈ Context Precision
- `Hit Rate + Precision@K` ≈ Context Recall
- `Evidence Grounding + Source Citation` ≈ Faithfulness
- `Category Match + Keyword Coverage` ≈ Answer Relevancy

**Strategy:** Deterministic for everyday CI/CD gates → RAGAS for periodic weekly quality deep-dives.

---

## ⚖️ Design Decisions & Tradeoffs

| Decision | What We Chose | Alternative | Why |
|---|---|---|---|
| Orchestration | LangGraph | LangChain Agents / CrewAI | State machines with conditional routing, explicit control flow |
| Vector DB | ChromaDB (persistent) | Pinecone / Weaviate | Zero-config MVP, metadata filtering. Pinecone for scale later |
| LLM | GPT-4o-mini (temp=0.1) | GPT-4o / Claude 3.5 | 90% quality at 10% cost. Low temp for consistent JSON |
| Chunking | Bounday aware + Log-aware | semantic/Fixed-size / Recursive | Preserves document structure, respects timestamp boundaries |
| Log Ingestion | NOT ingested to ChromaDB | Ingest all 3 types | No agent retrieves logs from RAG. Only ingest what's used |
| Evaluation | Custom deterministic | RAGAS / LLM-as-judge | Free, instant, CI/CD friendly, 25+ domain-specific metrics |
| Pipeline | Sequential agents | Parallel / async | Data dependencies require sequence. Parallel is future work |
| Observability | LangSmith | Langfuse / custom | Native LangChain integration, zero-code tracing, eval scoring |

---

## 🚀 Future Enhancements

### ⚡ Performance Optimization
- **Parallel Agent Execution:** Correlation + Remediation can run simultaneously (both only need `root_causes`) → 70s → 45s (35% faster)
- **Semantic Caching:** Cache at embedding level (similar queries) + response level (identical inputs) via `CacheBackedEmbeddings`
- **Streaming Responses:** WebSocket for real-time agent progress

### 🔍 RAG Quality Improvements
- **Hybrid Search (BM25 + Semantic):** Pure semantic misses exact error codes; BM25 catches `ERR-DB-POOL-001` literally
- **Feedback Loop:** Engineers mark "Was root cause correct? Y/N" → builds labeled dataset → improves prompts + retrieval
- **Scheduled RAGAS Deep-Dives:** Weekly faithfulness + answer_correctness checks

### 📏 Large Log Handling
- **Pre-Chunking by Time Windows:** Split huge logs into 5-min windows
- **Map-Reduce Pattern:** Parse each chunk independently, merge into unified state
- **Smart Truncation:** Keep first/last N lines + all ERROR/FATAL lines

### 🏢 Enterprise Readiness
- **Authentication:** RBAC with OAuth2/JWT (SRE, admin, viewer roles)
- **Scalable Infrastructure:** Managed vector DB (Pinecone / Azure AI Search), Prometheus / Datadog metrics
- **Integrations:** Slack/Teams bot, PagerDuty webhook, service dependency graph for topology-aware correlation

---

## 📂 Project Structure

```
incident_tage/
├── src/
│   ├── main.py                    # FastAPI app + lifespan
│   ├── config.py                  # Pydantic Settings (extra='ignore')
│   ├── agents/
│   │   ├── log_parser.py          # Agent 1: Log Parser
│   │   ├── root_cause.py          # Agent 2: Root Cause Analyzer (RAG)
│   │   ├── correlation.py         # Agent 3: Correlation Engine
│   │   └── remediation.py         # Agent 4: Remediation Agent (RAG)
│   ├── graph/
│   │   └── pipeline.py            # LangGraph pipeline + build_graph()
│   ├── rag/
│   │   ├── retriever.py           # IncidentRetriever with domain-specific retrieval
│   │   └── ingester.py            # IncidentDataIngester (auto-ingestion)
│   ├── security/
│   │   ├── pii_masker.py          # Presidio + regex PII masking
│   │   └── audit_logger.py        # Structured audit logging (JSONL)
│   └── frontend/
│       └── app.py                 # Streamlit UI
├── evaluation/
│   ├── run_all_evals.py           # Master runner for all 3 levels
│   ├── eval_rag.py                # Level 1: Retrieval evaluation
│   ├── eval_agents.py             # Level 2: Agent-level evaluation
│   ├── eval_end_to_end.py         # Level 3: End-to-end evaluation
│   └── results/                   # JSON results for CI/CD
├── mock_data/
│   ├── runbooks/                  # 4 runbook .md files
│   ├── past_incidents/            # 3 past incident .json files
│   └── test_logs/                 # Sample log files for testing
├── chroma_db/                     # Persistent ChromaDB storage
├── .env.example                   # Environment variable template
├── requirements.txt               # Python dependencies
└── README.md                      # This file
```

---

## 📜 License

This project was built as a technical evaluation task. For questions or collaboration, reach out to [Sameep Panigrahi](https://github.com/SameepPanigrahi).
