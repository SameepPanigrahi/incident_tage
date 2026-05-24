#!/usr/bin/env python3
"""
evaluation/eval_rag.py — Level 1: RAG Retrieval Evaluation

Tests whether ChromaDB returns the correct documents for incident-related queries.
Logs results to LangSmith for dashboard tracking.

Usage:
    cd incident-rca-assistant
    python -m evaluation.eval_rag
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

# ── Add project root to path ──
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import get_settings
from src.rag.vector_store import ChromaVectorStore
from src.rag.retriever import IncidentRetriever

# ═══════════════════════════════════════════════════════════
# GOLDEN TEST CASES — 10 queries covering all scenarios
# ═══════════════════════════════════════════════════════════

RETRIEVAL_TEST_CASES = [
    # ── Auth Service / DB Pool ──
    {
        "id": "R-001",
        "query": "database connection pool exhaustion fix procedures",
        "expected_sources": ["database_troubleshooting.md", "incident_001.json"],
        "filter_type": None,
        "top_k": 5,
    },
    {
        "id": "R-002",
        "query": "ERR-DB-POOL-001 connection leak error handling",
        "expected_sources": ["database_troubleshooting.md", "incident_001.json"],
        "filter_type": None,
        "top_k": 5,
    },
    {
        "id": "R-003",
        "query": "kill idle database connections pg_terminate_backend",
        "expected_sources": ["database_troubleshooting.md"],
        "filter_type": "runbook",
        "top_k": 5,
    },
    # ── Payment / Memory Leak ──
    {
        "id": "R-004",
        "query": "Java OutOfMemoryError heap space memory leak",
        "expected_sources": ["memory_leak_diagnosis.md", "incident_002.json"],
        "filter_type": None,
        "top_k": 5,
    },
    {
        "id": "R-005",
        "query": "unbounded cache TransactionCache OOM kill remediation",
        "expected_sources": ["memory_leak_diagnosis.md", "incident_002.json"],
        "filter_type": None,
        "top_k": 5,
    },
    # ── API Gateway / Timeout Cascade ──
    {
        "id": "R-006",
        "query": "cascading timeout circuit breaker thread pool exhaustion",
        "expected_sources": ["timeout_cascade_prevention.md", "incident_003.json"],
        "filter_type": None,
        "top_k": 5,
    },
    {
        "id": "R-007",
        "query": "missing database index full table scan slow query",
        "expected_sources": ["database_troubleshooting.md", "incident_003.json"],
        "filter_type": None,
        "top_k": 5,
    },
    # ── Deployment / Rollback ──
    {
        "id": "R-008",
        "query": "kubernetes rollback deployment kubectl rollout undo",
        "expected_sources": ["deployment_rollback_sop.md"],
        "filter_type": "runbook",
        "top_k": 5,
    },
    # ── Cross-cutting ──
    {
        "id": "R-009",
        "query": "circuit breaker configuration timeout tuning resilience4j",
        "expected_sources": ["timeout_cascade_prevention.md"],
        "filter_type": "runbook",
        "top_k": 5,
    },
    {
        "id": "R-010",
        "query": "GC pause stop the world heap dump memory profiling",
        "expected_sources": ["memory_leak_diagnosis.md"],
        "filter_type": "runbook",
        "top_k": 5,
    },
]


def evaluate_retrieval() -> dict:
    """
    Run retrieval evaluation on all test cases.
    Returns dict with per-query results and summary metrics.
    """
    settings = get_settings()
    vs = ChromaVectorStore(settings)
    retriever = IncidentRetriever(vs, settings)

    print("=" * 70)
    print("  LEVEL 1: RAG RETRIEVAL EVALUATION")
    print("=" * 70)

    results = []
    hits = 0
    total_precision = 0.0
    mrr_sum = 0.0
    all_expected_sources = set()
    all_found_sources = set()

    for tc in RETRIEVAL_TEST_CASES:
        # Retrieve documents
        docs = retriever.retrieve(
            query=tc["query"],
            filter_type=tc.get("filter_type"),
            top_k=tc.get("top_k", 5),
        )
        retrieved_sources = [d.metadata.get("source", "") for d in docs]

        # Track all expected sources
        for s in tc["expected_sources"]:
            all_expected_sources.add(s)

        # ── Hit Rate ──
        hit = any(
            exp in ret
            for exp in tc["expected_sources"]
            for ret in retrieved_sources
        )
        if hit:
            hits += 1

        # ── Precision@K ──
        relevant_count = sum(
            1 for src in retrieved_sources if src in tc["expected_sources"]
        )
        precision = relevant_count / len(retrieved_sources) if retrieved_sources else 0
        total_precision += precision

        # ── MRR ──
        rr = 0.0
        for rank, src in enumerate(retrieved_sources, 1):
            if src in tc["expected_sources"]:
                rr = 1.0 / rank
                all_found_sources.add(src)
                break
        mrr_sum += rr

        # ── Store result ──
        result = {
            "id": tc["id"],
            "query": tc["query"],
            "expected_sources": tc["expected_sources"],
            "retrieved_sources": retrieved_sources,
            "hit": hit,
            "precision": round(precision, 3),
            "reciprocal_rank": round(rr, 3),
        }
        results.append(result)

        # ── Print ──
        icon = "✅ HIT " if hit else "❌ MISS"
        print(f"\n  {icon} | [{tc['id']}] {tc['query'][:55]}...")
        print(f"         Expected:  {tc['expected_sources']}")
        print(f"         Retrieved: {retrieved_sources[:3]}{'...' if len(retrieved_sources) > 3 else ''}")
        print(f"         Precision: {precision:.1%} | RR: {rr:.3f}")

    # ── Summary ──
    n = len(RETRIEVAL_TEST_CASES)
    hit_rate = hits / n
    avg_precision = total_precision / n
    mrr = mrr_sum / n
    source_coverage = len(all_found_sources) / len(all_expected_sources) if all_expected_sources else 0

    summary = {
        "total_queries": n,
        "hits": hits,
        "hit_rate": round(hit_rate, 3),
        "avg_precision": round(avg_precision, 3),
        "mrr": round(mrr, 3),
        "source_coverage": round(source_coverage, 3),
        "sources_found": sorted(all_found_sources),
        "sources_missed": sorted(all_expected_sources - all_found_sources),
        "timestamp": datetime.now().isoformat(),
    }

    print(f"\n{'=' * 70}")
    print(f"  RETRIEVAL EVALUATION SUMMARY")
    print(f"{'=' * 70}")
    print(f"  Context Hit Rate:     {hit_rate:.1%}  ({hits}/{n})")
    print(f"  Avg Precision@K:      {avg_precision:.1%}")
    print(f"  Mean Reciprocal Rank: {mrr:.3f}")
    print(f"  Source Coverage:      {source_coverage:.1%}")
    if summary["sources_missed"]:
        print(f"  ⚠️  Sources never found: {summary['sources_missed']}")
    print(f"{'=' * 70}")

    # ── Save results ──
    results_dir = Path("evaluation/results")
    results_dir.mkdir(parents=True, exist_ok=True)
    output = {"summary": summary, "details": results}
    (results_dir / "retrieval_results.json").write_text(
        json.dumps(output, indent=2), encoding="utf-8"
    )
    print(f"\n  💾 Results saved to evaluation/results/retrieval_results.json")

    return output


def log_to_langsmith(results: dict) -> None:
    """Log retrieval evaluation results to LangSmith."""
    # try:
    #     from langsmith import Client

    #     client = Client()
    #     dataset_name = "retrieval-eval"

    #     # Create or get dataset
    #     try:
    #         dataset = client.create_dataset(
    #             dataset_name=dataset_name,
    #             description="RAG retrieval evaluation for Incident RCA Assistant",
    #         )
    #     except Exception:
    #         datasets = list(client.list_datasets(dataset_name=dataset_name))
    #         dataset = datasets[0] if datasets else None

    #     if dataset:
    #         for r in results["details"]:
    #             client.create_example(
    #                 inputs={"query": r["query"], "filter_type": r.get("filter_type")},
    #                 outputs={
    #                     "hit": r["hit"],
    #                     "precision": r["precision"],
    #                     "reciprocal_rank": r["reciprocal_rank"],
    #                     "retrieved_sources": r["retrieved_sources"],
    #                 },
    #                 dataset_id=dataset.id,
    #             )
    #         print(f"  ☁️  Logged {len(results['details'])} examples to LangSmith dataset: {dataset_name}")
    # except ImportError:
    #     print("  ⚠️  langsmith not installed — skipping LangSmith logging")
    # except Exception as e:
    #     print(f"  ⚠️  LangSmith logging failed: {e}")
    try:
        from langsmith import Client
        from langsmith.run_trees import RunTree

        client = Client()

        # ── Log each query as a scored run ──
        for r in results["details"]:
            run = RunTree(
                name=f"retrieval-{r['id']}",
                run_type="chain",
                inputs={"query": r["query"]},
                outputs={
                    "retrieved_sources": r["retrieved_sources"],
                    "hit": r["hit"],
                },
                project_name="incident-rca-eval",
            )
            run.end(outputs=run.outputs)
            run.post()

            # Attach scores as feedback
            client.create_feedback(
                run_id=run.id,
                key="hit_rate",
                score=1.0 if r["hit"] else 0.0,
                comment=f"Hit: {r['hit']}",
            )
            client.create_feedback(
                run_id=run.id,
                key="precision_at_k",
                score=r["precision"],
                comment=f"Precision: {r['precision']}",
            )
            client.create_feedback(
                run_id=run.id,
                key="mrr",
                score=r["reciprocal_rank"],
                comment=f"MRR: {r['reciprocal_rank']}",
            )

        # ── Log summary as one final run ──
        summary_run = RunTree(
            name="retrieval-summary",
            run_type="chain",
            inputs={"level": "Level 1: Retrieval", "total_queries": results["summary"]["total_queries"]},
            outputs=results["summary"],
            project_name="incident-rca-eval",
        )
        summary_run.end(outputs=summary_run.outputs)
        summary_run.post()

        client.create_feedback(run_id=summary_run.id, key="hit_rate", score=results["summary"]["hit_rate"])
        client.create_feedback(run_id=summary_run.id, key="avg_precision_at_k", score=results["summary"]["avg_precision"])
        client.create_feedback(run_id=summary_run.id, key="mrr", score=results["summary"]["mrr"])

        print(f"  ☁️  Logged {len(results['details'])} retrieval runs + 3 scores to LangSmith project: incident-rca-eval")

    except ImportError:
        print("  ⚠️  langsmith not installed — skipping")
    except Exception as e:
        print(f"  ⚠️  LangSmith logging failed: {e}")


if __name__ == "__main__":
    results = evaluate_retrieval()
    log_to_langsmith(results)
