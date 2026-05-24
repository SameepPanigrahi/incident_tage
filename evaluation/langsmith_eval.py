#!/usr/bin/env python3
"""
evaluation/langsmith_eval.py — LangSmith Native Evaluation

Usage:
    cd incident-rca-assistant
    python -m evaluation.langsmith_eval
"""

import sys
import os
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langsmith import Client
from langsmith.evaluation import evaluate
from langchain.callbacks.manager import tracing_v2_enabled
from src.config import get_settings
from src.agents.graph import build_graph


# ═══════════════════════════════════════════════════════════
# Step 1: Build the pipeline (module-level so evaluate() can use it)
# ═══════════════════════════════════════════════════════════

settings = get_settings()
graph, retriever, vs = build_graph(settings)


# ═══════════════════════════════════════════════════════════
# Step 2: Define the target function — THIS IS "run_pipeline"
# ═══════════════════════════════════════════════════════════

def run_pipeline(inputs: dict) -> dict:
    """The function LangSmith calls for each test case."""
    initial_state = {
        "incident_id": inputs["incident_id"],
        "raw_logs": inputs["logs"],
        "additional_context": inputs.get("context", ""),
        "parsed_entries": [], "impacted_services": [],
        "key_timestamps": [], "error_patterns": [],
        "incident_summary": {}, "root_causes": [],
        "retrieved_runbook_context": "",
        "correlated_anomalies": [], "remediation_steps": [],
        "retrieved_remediation_context": "", "messages": [],
    }

    with tracing_v2_enabled():
        final = graph.invoke(initial_state)

    return {
        "severity": final.get("incident_summary", {}).get("severity", ""),
        "root_causes": final.get("root_causes", []),
        "impacted_services": final.get("impacted_services", []),
        "remediation_steps": final.get("remediation_steps", []),
        "correlated_anomalies": final.get("correlated_anomalies", []),
    }


# ═══════════════════════════════════════════════════════════
# Step 3: Define custom evaluators
# ═══════════════════════════════════════════════════════════

def severity_match(run, example) -> dict:
    """Check if predicted severity matches expected."""
    predicted = run.outputs.get("severity", "").lower()
    expected = example.outputs.get("expected_severity", "").lower()
    return {"key": "severity_match", "score": 1.0 if predicted == expected else 0.0}


def root_cause_category_match(run, example) -> dict:
    """Check if expected root cause category was identified."""
    rcs = run.outputs.get("root_causes", [])
    all_text = " ".join(str(rc) for rc in rcs).lower()
    expected = example.outputs.get("expected_category", "").lower()
    return {"key": "category_match", "score": 1.0 if expected in all_text else 0.0}


def service_coverage(run, example) -> dict:
    """Check if expected services were identified."""
    predicted = set(s.lower() for s in run.outputs.get("impacted_services", []))
    expected = set(s.lower() for s in example.outputs.get("expected_services", []))
    if not expected:
        return {"key": "service_coverage", "score": 1.0}
    overlap = len(predicted & expected) / len(expected)
    return {"key": "service_coverage", "score": overlap}


def remediation_quality(run, example) -> dict:
    """Check remediation step count and quality."""
    steps = run.outputs.get("remediation_steps", [])
    min_steps = example.outputs.get("min_remediation_steps", 3)
    has_enough = len(steps) >= min_steps
    has_immediate = any(
        s.get("priority", "").lower() == "immediate" for s in steps
    )
    score = (0.5 if has_enough else 0.0) + (0.5 if has_immediate else 0.0)
    return {"key": "remediation_quality", "score": score}


# ═══════════════════════════════════════════════════════════
# Step 4: Create dataset + run evaluation
# ═══════════════════════════════════════════════════════════

def main():
    client = Client()
    dataset_name = "incident-rca-golden"

    # ── Create or get dataset ──
    try:
        dataset = client.create_dataset(
            dataset_name=dataset_name,
            description="Golden test cases for Incident RCA pipeline",
        )
        print(f"✅ Created new dataset: {dataset_name}")
    except Exception:
        datasets = list(client.list_datasets(dataset_name=dataset_name))
        dataset = datasets[0]
        print(f"📂 Using existing dataset: {dataset_name}")

    # ── Add golden examples ──
    golden_examples = [
        {
            "inputs": {
                "incident_id": "GOLD-001",
                "logs": Path("mock_data/incident_logs/auth_service_outage.log").read_text(),
                "context": "auth-service v2.5.0 deployed 30 minutes ago",
            },
            "outputs": {
                "expected_severity": "critical",
                "expected_category": "db_connection_exhaustion",
                "expected_services": ["auth-service", "api-gateway"],
                "min_remediation_steps": 3,
            },
        },
        {
            "inputs": {
                "incident_id": "GOLD-002",
                "logs": Path("mock_data/incident_logs/payment_latency_spike.log").read_text(),
                "context": "payment-service v3.1.0 deployed 1 hour ago",
            },
            "outputs": {
                "expected_severity": "critical",
                "expected_category": "memory_leak",
                "expected_services": ["payment-service"],
                "min_remediation_steps": 3,
            },
        },
        {
            "inputs": {
                "incident_id": "GOLD-003",
                "logs": Path("mock_data/incident_logs/api_gateway_timeout.log").read_text(),
                "context": "No recent deployments",
            },
            "outputs": {
                "expected_severity": "high",
                "expected_category": "api_timeout_propagation",
                "expected_services": ["inventory-service", "api-gateway"],
                "min_remediation_steps": 3,
            },
        },
    ]

    for ex in golden_examples:
        client.create_example(
            inputs=ex["inputs"],
            outputs=ex["outputs"],
            dataset_id=dataset.id,
        )
    print(f"📝 Added {len(golden_examples)} golden examples")

    # ── Run evaluation ──
    print("\n🚀 Running LangSmith evaluation...")

    eval_results = evaluate(
        run_pipeline,                # ← The function defined above
        data=dataset_name,
        evaluators=[
            severity_match,
            root_cause_category_match,
            service_coverage,
            remediation_quality,
        ],
        experiment_prefix="incident-rca-eval",
        max_concurrency=1,
    )

    print("\n✅ Evaluation complete!")
    print("   View results at: https://smith.langchain.com")
    print(f"   Dataset: {dataset_name}")
    print()
    print("   📊 In the LangSmith dashboard you will see:")
    print("   ├── severity_match:        score per scenario")
    print("   ├── category_match:        score per scenario")
    print("   ├── service_coverage:      score per scenario")
    print("   └── remediation_quality:   score per scenario")

    return eval_results


if __name__ == "__main__":
    main()