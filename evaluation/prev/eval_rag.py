from __future__ import annotations

import json
import logging
from pathlib import Path

from src.config import get_settings
from src.rag.vector_store import ChromaVectorStore
from src.rag.retriever import IncidentRetriever

logger = logging.getLogger(__name__)


def load_golden_dataset(path: str = "evaluation/golden_dataset.json") -> list[dict]:
    """Load the golden Q&A dataset."""
    data = json.loads(Path(path).read_text())
    return data["questions"]


def evaluate_retrieval(retriever: IncidentRetriever, questions: list[dict]) -> dict:
    """Run retrieval on each question and compute basic metrics.

    Metrics computed:
    - context_hit_rate: % of questions where at least one retrieved doc
      comes from the expected source.
    - avg_docs_retrieved: average number of documents returned.
    """
    hits = 0
    total_docs = 0

    results = []
    for q in questions:
        # Retrieve
        docs = retriever.retrieve(q["question"], top_k=5)
        total_docs += len(docs)

        # Check if any retrieved doc matches expected source
        expected_sources = [
            s.strip() for s in q.get("ground_truth_context", "").split(",")
        ]
        retrieved_sources = [d.metadata.get("source", "") for d in docs]
        hit = any(
            expected in retrieved
            for expected in expected_sources
            for retrieved in retrieved_sources
        )
        if hit:
            hits += 1

        results.append({
            "id": q["id"],
            "category": q["category"],
            "question": q["question"],
            "expected_sources": expected_sources,
            "retrieved_sources": retrieved_sources,
            "hit": hit,
            "num_docs": len(docs),
        })

    metrics = {
        "context_hit_rate": round(hits / len(questions), 3) if questions else 0,
        "avg_docs_retrieved": round(total_docs / len(questions), 1) if questions else 0,
        "total_questions": len(questions),
        "total_hits": hits,
    }

    return {"metrics": metrics, "details": results}


def main():
    """Run evaluation and print results."""
    settings = get_settings()
    vector_store = ChromaVectorStore(settings)
    retriever = IncidentRetriever(vector_store, settings)

    questions = load_golden_dataset()
    print(f"Loaded {len(questions)} evaluation questions.")

    results = evaluate_retrieval(retriever, questions)

    print("\n" + "=" * 60)
    print("RETRIEVAL EVALUATION RESULTS")
    print("=" * 60)
    for key, val in results["metrics"].items():
        print(f"  {key}: {val}")
    print("=" * 60)

    # Per-question breakdown
    print("\nPer-Question Results:")
    for r in results["details"]:
        status = "HIT" if r["hit"] else "MISS"
        print(f"  [{status}] {r['id']} ({r['category']}): {r['question'][:60]}...")

    # Save
    output_path = "evaluation/eval_results.json"
    Path(output_path).write_text(json.dumps(results, indent=2))
    print(f"\nResults saved to {output_path}")

    # Note about RAGAS
    print("\n--- RAGAS Integration Note ---")
    print("For full RAGAS evaluation (faithfulness, answer_relevancy,")
    print("context_precision, context_recall), install ragas and run:")
    print("  from ragas import evaluate")
    print("  from ragas.metrics import faithfulness, answer_relevancy,")
    print("                            context_precision, context_recall")
    print("  results = evaluate(dataset, metrics=[...], llm=your_llm)")
    print("This requires generating LLM answers for each question first.")


if __name__ == "__main__":
    main()
