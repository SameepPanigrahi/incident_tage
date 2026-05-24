#!/usr/bin/env python3
"""
evaluation/run_all_evals.py — Master Evaluation Runner

Runs all 3 evaluation levels and prints a combined report card.
All results are saved to evaluation/results/ and logged to LangSmith.

Usage:
    cd incident-rca-assistant
    python -m evaluation.run_all_evals
"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    print()
    print("╔" + "═" * 68 + "╗")
    print("║" + "  🧪 INCIDENT RCA ASSISTANT — COMPLETE EVALUATION SUITE".center(68) + "║")
    print("╚" + "═" * 68 + "╝")

    overall_start = time.time()
    report = {}

    # ═══════ LEVEL 1: RETRIEVAL ═══════
    print("\n\n🔍 Running Level 1: RAG Retrieval Evaluation...")
    print("   (No LLM calls — tests vector search only)")
    try:
        from evaluation.eval_rag import evaluate_retrieval, log_to_langsmith as log_rag
        rag_results = evaluate_retrieval()
        log_rag(rag_results)
        report["Level 1: Retrieval"] = {
            "hit_rate": rag_results["summary"]["hit_rate"],
            "avg_precision": rag_results["summary"]["avg_precision"],
            "mrr": rag_results["summary"]["mrr"],
            "status": "✅" if rag_results["summary"]["hit_rate"] >= 0.7 else "⚠️",
        }
    except Exception as e:
        print(f"   ❌ Level 1 failed: {e}")
        report["Level 1: Retrieval"] = {"status": "❌", "error": str(e)}

    # ═══════ LEVEL 2: AGENT-LEVEL ═══════
    print("\n\n🤖 Running Level 2: Agent-Level Evaluation...")
    print("   (12 LLM calls — tests each agent individually)")
    try:
        from evaluation.eval_agents import run_all_agent_evals, log_to_langsmith as log_agents
        agent_results = run_all_agent_evals()
        log_agents(agent_results)
        report["Level 2: Agents"] = {
            "pass_rate": agent_results["summary"]["overall_rate"],
            "passed": agent_results["summary"]["total_pass"],
            "total": agent_results["summary"]["total_tests"],
            "status": "✅" if agent_results["summary"]["overall_rate"] >= 0.7 else "⚠️",
        }
    except Exception as e:
        print(f"   ❌ Level 2 failed: {e}")
        report["Level 2: Agents"] = {"status": "❌", "error": str(e)}

    # ═══════ LEVEL 3: END-TO-END ═══════
    print("\n\n🚀 Running Level 3: End-to-End Pipeline Evaluation...")
    print("   (Full pipeline × 3 scenarios — 12 LLM calls)")
    try:
        from evaluation.eval_end_to_end import evaluate_end_to_end, log_to_langsmith as log_e2e
        e2e_results = evaluate_end_to_end()
        log_e2e(e2e_results)
        report["Level 3: End-to-End"] = {
            "pass_rate": e2e_results["summary"]["overall_rate"],
            "passed": e2e_results["summary"]["total_pass"],
            "total": e2e_results["summary"]["total_checks"],
            "status": "✅" if e2e_results["summary"]["overall_rate"] >= 0.7 else "⚠️",
        }
    except Exception as e:
        print(f"   ❌ Level 3 failed: {e}")
        report["Level 3: End-to-End"] = {"status": "❌", "error": str(e)}

    total_elapsed = round(time.time() - overall_start, 1)

    # ═══════ COMBINED REPORT CARD ═══════
    print("\n\n")
    print("╔" + "═" * 68 + "╗")
    print("║" + "  📊 COMBINED EVALUATION REPORT CARD".center(68) + "║")
    print("╠" + "═" * 68 + "╣")

    for level_name, level_data in report.items():
        status = level_data.get("status", "❌")
        if "pass_rate" in level_data:
            detail = f"{level_data['pass_rate']:.0%} pass rate"
        elif "hit_rate" in level_data:
            detail = f"{level_data['hit_rate']:.0%} hit rate, {level_data['mrr']:.3f} MRR"
        else:
            detail = level_data.get("error", "Unknown error")[:40]

        line = f"  {status}  {level_name:30s}  {detail}"
        print("║" + line.ljust(68) + "║")

    print("╠" + "═" * 68 + "╣")
    line = f"  ⏱️  Total evaluation time: {total_elapsed}s"
    print("║" + line.ljust(68) + "║")
    line = f"  📅  Run date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    print("║" + line.ljust(68) + "║")
    print("╚" + "═" * 68 + "╝")

    # ═══════ LOG COMBINED REPORT TO LANGSMITH ═══════
    try:
        from langsmith import Client

        client = Client()
        dataset_name = "evaluation-report"
        try:
            dataset = client.create_dataset(
                dataset_name=dataset_name,
                description="Combined evaluation report card — all 3 levels",
            )
        except Exception:
            datasets = list(client.list_datasets(dataset_name=dataset_name))
            dataset = datasets[0] if datasets else None

        if dataset:
            # Log each level as a scored example
            for level_name, level_data in report.items():
                if level_name == "metadata":
                    continue

                # Build score from available data
                if "hit_rate" in level_data:
                    score = level_data["hit_rate"]
                elif "pass_rate" in level_data:
                    score = level_data["pass_rate"]
                else:
                    score = 0.0

                client.create_example(
                    inputs={"level": level_name, "run_date": datetime.now().isoformat()},
                    outputs={"score": score, **{k: v for k, v in level_data.items() if k != "status"}},
                    dataset_id=dataset.id,
                )
            print(f"  ☁️  Combined report logged to LangSmith dataset: {dataset_name}")
    except Exception as e:
        print(f"  ⚠️  LangSmith logging failed: {e}")

    # ── Save combined report ──
    results_dir = Path("evaluation/results")
    results_dir.mkdir(parents=True, exist_ok=True)
    report["metadata"] = {
        "total_time_seconds": total_elapsed,
        "timestamp": datetime.now().isoformat(),
    }
    (results_dir / "combined_report.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )
    print(f"\n  💾 Combined report saved to evaluation/results/combined_report.json")
    print(f"  ☁️  All results logged to LangSmith (check your dashboard)")


if __name__ == "__main__":
    main()
