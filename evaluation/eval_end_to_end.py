#!/usr/bin/env python3
"""
evaluation/eval_end_to_end.py — Level 3: End-to-End Pipeline Evaluation

Runs the full LangGraph pipeline on known incident scenarios and checks
12+ assertions per scenario. Logs results to LangSmith.

Usage:
    cd incident-rca-assistant
    python -m evaluation.eval_end_to_end
"""

import sys
import os
import json
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain.callbacks.manager import tracing_v2_enabled
from src.config import get_settings
from src.agents.graph import build_graph

# ═══════════════════════════════════════════════════════════
# END-TO-END SCENARIOS
# ═══════════════════════════════════════════════════════════

E2E_SCENARIOS = [
    {
        "name": "Auth Service Outage — DB Connection Pool Exhaustion",
        "incident_id": "EVAL-E2E-001",
        "log_file": "mock_data/incident_logs/auth_service_outage.log",
        "context": "auth-service v2.5.0 deployed 30 minutes before outage",
        "expected": {
            "severity": "critical",
            "root_cause_category": "db_connection_exhaustion",
            "min_services": 3,
            "must_include_services": ["auth-service", "api-gateway"],
            "min_root_causes": 1,
            "max_root_causes": 3,
            "root_cause_must_mention": ["connection", "pool"],
            "min_remediation_steps": 3,
            "remediation_must_mention": ["restart", "connection"],
            "min_anomalies": 2,
            "max_processing_seconds": 60,
        },
    },
    {
        "name": "Payment Service — Memory Leak After Deployment",
        "incident_id": "EVAL-E2E-002",
        "log_file": "mock_data/incident_logs/payment_latency_spike.log",
        "context": "payment-service v3.1.0 deployed 1 hour ago. No other changes.",
        "expected": {
            "severity": "critical",
            "root_cause_category": "memory_leak",
            "min_services": 2,
            "must_include_services": ["payment-service"],
            "min_root_causes": 1,
            "max_root_causes": 3,
            "root_cause_must_mention": ["memory", "heap"],
            "min_remediation_steps": 3,
            "remediation_must_mention": ["rollback", "restart"],
            "min_anomalies": 1,
            "max_processing_seconds": 60,
        },
    },
    {
        "name": "API Gateway — Cascading Timeout from Missing Index",
        "incident_id": "EVAL-E2E-003",
        "log_file": "mock_data/incident_logs/api_gateway_timeout.log",
        "context": "No recent deployments. Database migration scheduled for today.",
        "expected": {
            "severity": "high",
            "root_cause_category": "api_timeout_propagation",
            "min_services": 3,
            "must_include_services": ["inventory-service", "api-gateway"],
            "min_root_causes": 1,
            "max_root_causes": 3,
            "root_cause_must_mention": ["timeout", "index"],
            "min_remediation_steps": 3,
            "remediation_must_mention": ["index", "circuit"],
            "min_anomalies": 2,
            "max_processing_seconds": 60,
        },
    },
]


def evaluate_end_to_end() -> dict:
    """
    Run full pipeline evaluation on all E2E scenarios.
    Returns dict with per-scenario results and final pass rate.
    """
    settings = get_settings()
    graph, retriever, vs = build_graph(settings)

    print("=" * 70)
    print("  LEVEL 3: END-TO-END PIPELINE EVALUATION")
    print("=" * 70)

    all_results = []
    total_checks = 0
    total_pass = 0

    for sc in E2E_SCENARIOS:
        print(f"\n{'─' * 70}")
        print(f"  Scenario: {sc['name']}")
        print(f"{'─' * 70}")

        logs = Path(sc["log_file"]).read_text(encoding="utf-8")
        initial_state = {
            "incident_id": sc["incident_id"],
            "raw_logs": logs,
            "additional_context": sc["context"],
            "parsed_entries": [], "impacted_services": [],
            "key_timestamps": [], "error_patterns": [],
            "incident_summary": {}, "root_causes": [],
            "retrieved_runbook_context": "",
            "correlated_anomalies": [], "remediation_steps": [],
            "retrieved_remediation_context": "", "messages": [],
        }

        start = time.time()
        with tracing_v2_enabled():
            final = graph.invoke(initial_state)
        elapsed = round(time.time() - start, 1)

        exp = sc["expected"]
        checks = {}

        # ═══════ SERVICES ═══════
        services = [s.lower() for s in final.get("impacted_services", [])]
        checks["services_count"] = len(services) >= exp["min_services"]
        checks["services_must_include"] = all(
            s.lower() in services for s in exp["must_include_services"]
        )

        # ═══════ ROOT CAUSES ═══════
        rcs = final.get("root_causes", [])
        checks["root_cause_count"] = exp["min_root_causes"] <= len(rcs) <= exp["max_root_causes"]

        all_rc_text = json.dumps(rcs).lower()
        checks["root_cause_category"] = exp["root_cause_category"].lower() in all_rc_text

        checks["root_cause_has_evidence"] = all(
            len(rc.get("evidence", [])) > 0 for rc in rcs
        ) if rcs else False

        checks["root_cause_has_reasoning"] = all(
            len(rc.get("reasoning", "")) >= 30 for rc in rcs
        ) if rcs else False

        checks["root_cause_keywords"] = all(
            kw.lower() in all_rc_text for kw in exp["root_cause_must_mention"]
        )

        # ═══════ SEVERITY ═══════
        summary = final.get("incident_summary", {})
        severity = summary.get("severity", "").lower()
        checks["severity_match"] = severity == exp["severity"].lower()

        # ═══════ REMEDIATION ═══════
        steps = final.get("remediation_steps", [])
        checks["remediation_count"] = len(steps) >= exp["min_remediation_steps"]

        priorities = [s.get("priority", "").lower() for s in steps]
        checks["has_immediate_step"] = "immediate" in priorities

        # Priority ordering
        p_order = {"immediate": 0, "short-term": 1, "short_term": 1, "long-term": 2, "long_term": 2}
        p_vals = [p_order.get(p, 99) for p in priorities]
        checks["priority_ordering"] = p_vals == sorted(p_vals)

        sources = " ".join(str(s.get("source_document", "") or s.get("source", "")) for s in steps).lower()
        checks["has_source_citation"] = len(sources.strip()) > 5

        all_actions = " ".join(s.get("action", "") for s in steps).lower()
        checks["remediation_keywords"] = any(
            kw.lower() in all_actions for kw in exp["remediation_must_mention"]
        )

        # ═══════ CORRELATIONS ═══════
        anomalies = final.get("correlated_anomalies", [])
        checks["anomaly_count"] = len(anomalies) >= exp["min_anomalies"]

        scores = [a.get("correlation_score", -1) for a in anomalies]
        checks["scores_valid"] = all(0.0 <= s <= 1.0 for s in scores) if scores else False

        # ═══════ PERFORMANCE ═══════
        checks["processing_time"] = elapsed <= exp["max_processing_seconds"]

        # ═══════ PRINT RESULTS ═══════
        scenario_pass = 0
        scenario_total = 0
        for check_name, passed in checks.items():
            total_checks += 1
            scenario_total += 1
            if passed:
                total_pass += 1
                scenario_pass += 1
            icon = "✅" if passed else "❌"
            print(f"  {icon}  {check_name}")

        print(f"\n  ⏱️  Processing time: {elapsed}s")
        print(f"  📊  Scenario score: {scenario_pass}/{scenario_total} ({scenario_pass/scenario_total:.0%})")

        all_results.append({
            "name": sc["name"],
            "incident_id": sc["incident_id"],
            "checks": checks,
            "scenario_pass": scenario_pass,
            "scenario_total": scenario_total,
            "processing_time": elapsed,
        })

    # ═══════ FINAL SCORE ═══════
    overall_rate = total_pass / total_checks if total_checks else 0

    print(f"\n{'=' * 70}")
    print(f"  END-TO-END EVALUATION — FINAL RESULTS")
    print(f"{'=' * 70}")
    for r in all_results:
        rate = r["scenario_pass"] / r["scenario_total"]
        icon = "✅" if rate >= 0.8 else "⚠️" if rate >= 0.6 else "❌"
        print(f"  {icon}  {r['name'][:50]:50s}  {r['scenario_pass']}/{r['scenario_total']}  ({rate:.0%})")

    print(f"\n  {'─' * 50}")
    icon = "🏆" if overall_rate >= 0.8 else "⚠️" if overall_rate >= 0.6 else "❌"
    print(f"  {icon}  FINAL SCORE: {total_pass}/{total_checks} ({overall_rate:.0%})")
    print(f"  {'─' * 50}")

    # ── Save ──
    results_dir = Path("evaluation/results")
    results_dir.mkdir(parents=True, exist_ok=True)
    output = {
        "summary": {
            "total_pass": total_pass, "total_checks": total_checks,
            "overall_rate": round(overall_rate, 3),
            "scenarios": len(E2E_SCENARIOS),
            "timestamp": datetime.now().isoformat(),
        },
        "details": all_results,
    }
    (results_dir / "e2e_results.json").write_text(
        json.dumps(output, indent=2, default=str), encoding="utf-8"
    )
    print(f"\n  💾 Results saved to evaluation/results/e2e_results.json")

    return output


def log_to_langsmith(results: dict) -> None:
    """Log end-to-end evaluation results to LangSmith."""
    try:
        from langsmith import Client

        client = Client()
        dataset_name = "e2e-eval"

        try:
            dataset = client.create_dataset(
                dataset_name=dataset_name,
                description="End-to-end pipeline evaluation for Incident RCA Assistant",
            )
        except Exception:
            datasets = list(client.list_datasets(dataset_name=dataset_name))
            dataset = datasets[0] if datasets else None

        if dataset:
            for r in results["details"]:
                client.create_example(
                    inputs={"scenario": r["name"], "incident_id": r["incident_id"]},
                    outputs={
                        "pass_rate": r["scenario_pass"] / r["scenario_total"],
                        "processing_time": r["processing_time"],
                        "checks": r["checks"],
                    },
                    dataset_id=dataset.id,
                )
            print(f"  ☁️  Logged {len(results['details'])} scenarios to LangSmith dataset: {dataset_name}")
    except ImportError:
        print("  ⚠️  langsmith not installed — skipping")
    except Exception as e:
        print(f"  ⚠️  LangSmith logging failed: {e}")


if __name__ == "__main__":
    results = evaluate_end_to_end()
    log_to_langsmith(results)
