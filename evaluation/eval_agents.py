
"""
evaluation/eval_agents.py — Level 2: Agent-Level Evaluation

Tests each of the 4 agents individually for correctness.
Logs results to LangSmith for dashboard tracking.

Usage:
    cd incident-rca-assistant
    python -m evaluation.eval_agents
"""

import sys
import os
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain.callbacks.manager import tracing_v2_enabled
from src.config import get_settings
from src.agents.graph import build_graph

# ═══════════════════════════════════════════════════════════
# TEST CASES
# ═══════════════════════════════════════════════════════════

LOG_PARSER_TESTS = [
    {
        "name": "Auth Service Outage",
        "log_file": "mock_data/incident_logs/auth_service_outage.log",
        "expected_services": {"auth-service", "db-pool-manager", "api-gateway", "user-service"},
        "expected_first_error_contains": "14:10",
        "min_error_patterns": 2,
        "min_parsed_entries": 10,
    },
    {
        "name": "Payment Latency Spike",
        "log_file": "mock_data/incident_logs/payment_latency_spike.log",
        "expected_services": {"payment-service", "deployment-controller", "memory-monitor", "load-balancer"},
        "expected_first_error_contains": "09:50",
        "min_error_patterns": 2,
        "min_parsed_entries": 10,
    },
    {
        "name": "API Gateway Timeout",
        "log_file": "mock_data/incident_logs/api_gateway_timeout.log",
        "expected_services": {"inventory-service", "order-service", "api-gateway", "notification-service"},
        "expected_first_error_contains": "16:07",
        "min_error_patterns": 2,
        "min_parsed_entries": 10,
    },
]

ROOT_CAUSE_TESTS = [
    {
        "name": "Auth → DB Pool Exhaustion",
        "log_file": "mock_data/incident_logs/auth_service_outage.log",
        "context": "auth-service v2.5.0 deployed 30 minutes ago",
        "expected_category": "db_connection_exhaustion",
        "expected_confidence": "high",
        "must_mention_keywords": ["connection", "pool", "exhausted"],
    },
    {
        "name": "Payment → Memory Leak",
        "log_file": "mock_data/incident_logs/payment_latency_spike.log",
        "context": "payment-service v3.1.0 deployed 1 hour ago",
        "expected_category": "memory_leak",
        "expected_confidence": "high",
        "must_mention_keywords": ["memory", "heap", "OOM"],
    },
    {
        "name": "API Gateway → Timeout Cascade",
        "log_file": "mock_data/incident_logs/api_gateway_timeout.log",
        "context": "No recent deployments. DB migration ran this morning.",
        "expected_category": "api_timeout_propagation",
        "expected_confidence": "high",
        "must_mention_keywords": ["timeout", "cascade", "index"],
    },
]

CORRELATION_TESTS = [
    {
        "name": "Auth Cascading Failure",
        "log_file": "mock_data/incident_logs/auth_service_outage.log",
        "context": "auth-service v2.5.0 deployed 30 minutes ago",
        "min_anomalies": 2,
        "must_include_services": ["auth-service", "api-gateway"],
    },
    {
        "name": "Payment Pod Cycling",
        "log_file": "mock_data/incident_logs/payment_latency_spike.log",
        "context": "payment-service v3.1.0 deployed 1 hour ago",
        "min_anomalies": 1,
        "must_include_services": ["payment-service"],
    },
    {
        "name": "API Timeout Chain",
        "log_file": "mock_data/incident_logs/api_gateway_timeout.log",
        "context": "No recent deployments",
        "min_anomalies": 2,
        "must_include_services": ["inventory-service", "api-gateway"],
    },
]

REMEDIATION_TESTS = [
    {
        "name": "DB Pool Fix",
        "log_file": "mock_data/incident_logs/auth_service_outage.log",
        "context": "auth-service v2.5.0 deployed 30 minutes ago",
        "min_steps": 3,
        "must_have_priorities": ["immediate"],
        "expected_source_contains": "database",
        "should_contain_keywords": ["terminate", "restart", "pool"],
    },
    {
        "name": "Memory Leak Fix",
        "log_file": "mock_data/incident_logs/payment_latency_spike.log",
        "context": "payment-service v3.1.0 deployed 1 hour ago",
        "min_steps": 3,
        "must_have_priorities": ["immediate"],
        "expected_source_contains": "memory",
        "should_contain_keywords": ["rollback", "restart", "heap"],
    },
    {
        "name": "Timeout Cascade Fix",
        "log_file": "mock_data/incident_logs/api_gateway_timeout.log",
        "context": "No recent deployments",
        "min_steps": 3,
        "must_have_priorities": ["immediate"],
        "expected_source_contains": "timeout",
        "should_contain_keywords": ["index", "circuit", "timeout"],
    },
]


def _build_initial_state(incident_id: str, logs: str, context: str) -> dict:
    """Build a clean initial state for graph invocation."""
    return {
        "incident_id": incident_id,
        "raw_logs": logs,
        "additional_context": context,
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


# ═══════════════════════════════════════════════════════════
# EVALUATOR 1: LOG PARSER
# ═══════════════════════════════════════════════════════════

def evaluate_log_parser(graph, settings) -> list:
    """Evaluate Agent 1 — Log Parser accuracy."""
    print("\n" + "─" * 70)
    print("  AGENT 1: LOG PARSER EVALUATION")
    print("─" * 70)

    results = []
    for tc in LOG_PARSER_TESTS:
        logs = Path(tc["log_file"]).read_text(encoding="utf-8")
        state = _build_initial_state(f"EVAL-LP-{tc['name'][:3]}", logs, "")

        with tracing_v2_enabled():
            final = graph.invoke(state)

        extracted_services = set(s.lower() for s in final.get("impacted_services", []))
        expected_services = set(s.lower() for s in tc["expected_services"])

        # ── Service F1 ──
        tp = len(extracted_services & expected_services)
        precision = tp / len(extracted_services) if extracted_services else 0
        recall = tp / len(expected_services) if expected_services else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

        # ── Timestamp check ──
        timestamps = final.get("key_timestamps", [])
        all_ts_text = json.dumps(timestamps).lower()
        ts_correct = tc["expected_first_error_contains"] in all_ts_text

        # ── Pattern count ──
        patterns = final.get("error_patterns", [])
        patterns_ok = len(patterns) >= tc["min_error_patterns"]

        # ── Entry count ──
        entries = final.get("parsed_entries", [])
        entries_ok = len(entries) >= tc["min_parsed_entries"]

        passed = f1 >= 0.6 and patterns_ok and entries_ok
        icon = "✅ PASS" if passed else "❌ FAIL"

        print(f"\n  {icon} | {tc['name']}")
        print(f"    Service F1:       {f1:.2f}  (P={precision:.2f}, R={recall:.2f})")
        print(f"    Services found:   {sorted(extracted_services)}")
        print(f"    Services expected:{sorted(expected_services)}")
        print(f"    Timestamp OK:     {ts_correct}")
        print(f"    Error patterns:   {len(patterns)} (min: {tc['min_error_patterns']})")
        print(f"    Entries parsed:   {len(entries)} (min: {tc['min_parsed_entries']})")

        results.append({
            "name": tc["name"], "agent": "log_parser",
            "service_f1": round(f1, 3), "timestamp_correct": ts_correct,
            "pattern_count": len(patterns), "entry_count": len(entries),
            "pass": passed,
        })

    return results


# ═══════════════════════════════════════════════════════════
# EVALUATOR 2: ROOT CAUSE ANALYZER
# ═══════════════════════════════════════════════════════════

def evaluate_root_cause(graph, settings) -> list:
    """Evaluate Agent 2 — Root Cause Analyzer accuracy."""
    print("\n" + "─" * 70)
    print("  AGENT 2: ROOT CAUSE ANALYZER EVALUATION")
    print("─" * 70)

    results = []
    for tc in ROOT_CAUSE_TESTS:
        logs = Path(tc["log_file"]).read_text(encoding="utf-8")
        state = _build_initial_state(f"EVAL-RC-{tc['name'][:3]}", logs, tc["context"])

        with tracing_v2_enabled():
            final = graph.invoke(state)

        root_causes = final.get("root_causes", [])
        categories = [rc.get("category", "").lower() for rc in root_causes]

        # ── Category match ──
        category_match = tc["expected_category"].lower() in " ".join(categories)

        # ── Confidence ──
        top_cause = root_causes[0] if root_causes else {}
        confidence = top_cause.get("confidence", "unknown").lower()
        confidence_match = confidence == tc["expected_confidence"]

        # ── Evidence grounding ──
        evidence = top_cause.get("evidence", [])
        has_evidence = len(evidence) >= 1

        # ── Reasoning quality ──
        reasoning = top_cause.get("reasoning", "")
        has_reasoning = len(reasoning) >= 30

        # ── Keyword check ──
        all_text = json.dumps(root_causes).lower()
        keywords_found = [kw for kw in tc["must_mention_keywords"] if kw.lower() in all_text]
        keyword_coverage = len(keywords_found) / len(tc["must_mention_keywords"])

        passed = category_match and has_evidence and has_reasoning and keyword_coverage >= 0.5
        icon = "✅ PASS" if passed else "❌ FAIL"

        print(f"\n  {icon} | {tc['name']}")
        print(f"    Expected category:  {tc['expected_category']}")
        print(f"    Got categories:     {categories}")
        print(f"    Category match:     {category_match}")
        print(f"    Confidence:         {confidence} (expected: {tc['expected_confidence']})")
        print(f"    Evidence items:     {len(evidence)}")
        print(f"    Reasoning length:   {len(reasoning)} chars")
        print(f"    Keywords found:     {keywords_found} / {tc['must_mention_keywords']}")

        results.append({
            "name": tc["name"], "agent": "root_cause",
            "category_match": category_match, "confidence_match": confidence_match,
            "evidence_count": len(evidence), "reasoning_length": len(reasoning),
            "keyword_coverage": round(keyword_coverage, 2), "pass": passed,
        })

    return results


# ═══════════════════════════════════════════════════════════
# EVALUATOR 3: CORRELATION ENGINE
# ═══════════════════════════════════════════════════════════

def evaluate_correlation(graph, settings) -> list:
    """Evaluate Agent 3 — Correlation Engine accuracy."""
    print("\n" + "─" * 70)
    print("  AGENT 3: CORRELATION ENGINE EVALUATION")
    print("─" * 70)

    results = []
    for tc in CORRELATION_TESTS:
        logs = Path(tc["log_file"]).read_text(encoding="utf-8")
        state = _build_initial_state(f"EVAL-CE-{tc['name'][:3]}", logs, tc["context"])

        with tracing_v2_enabled():
            final = graph.invoke(state)

        anomalies = final.get("correlated_anomalies", [])

        # ── Anomaly count ──
        count_ok = len(anomalies) >= tc["min_anomalies"]

        # ── Service coverage ──
        anomaly_services = set(a.get("service", "").lower() for a in anomalies)
        expected_services = set(s.lower() for s in tc["must_include_services"])
        service_hit = len(anomaly_services & expected_services)
        service_coverage = service_hit / len(expected_services) if expected_services else 0

        # ── Score validity (all between 0 and 1) ──
        scores = [a.get("correlation_score", -1) for a in anomalies]
        scores_valid = all(0.0 <= s <= 1.0 for s in scores) if scores else False

        # ── Description quality ──
        descriptions = [a.get("description", "") for a in anomalies]
        has_descriptions = all(len(d) > 20 for d in descriptions) if descriptions else False

        passed = count_ok and service_coverage >= 0.5 and scores_valid
        icon = "✅ PASS" if passed else "❌ FAIL"

        print(f"\n  {icon} | {tc['name']}")
        print(f"    Anomalies found:    {len(anomalies)} (min: {tc['min_anomalies']})")
        print(f"    Services in anomalies: {sorted(anomaly_services)}")
        print(f"    Expected services:  {sorted(expected_services)}")
        print(f"    Service coverage:   {service_coverage:.0%}")
        print(f"    Scores valid:       {scores_valid} ({scores})")
        print(f"    Has descriptions:   {has_descriptions}")

        results.append({
            "name": tc["name"], "agent": "correlation",
            "anomaly_count": len(anomalies), "service_coverage": round(service_coverage, 2),
            "scores_valid": scores_valid, "has_descriptions": has_descriptions,
            "pass": passed,
        })

    return results


# ═══════════════════════════════════════════════════════════
# EVALUATOR 4: REMEDIATION AGENT
# ═══════════════════════════════════════════════════════════

def evaluate_remediation(graph, settings) -> list:
    """Evaluate Agent 4 — Remediation Agent quality."""
    print("\n" + "─" * 70)
    print("  AGENT 4: REMEDIATION AGENT EVALUATION")
    print("─" * 70)

    results = []
    for tc in REMEDIATION_TESTS:
        logs = Path(tc["log_file"]).read_text(encoding="utf-8")
        state = _build_initial_state(f"EVAL-RM-{tc['name'][:3]}", logs, tc["context"])

        with tracing_v2_enabled():
            final = graph.invoke(state)

        steps = final.get("remediation_steps", [])

        # ── Step count ──
        count_ok = len(steps) >= tc["min_steps"]

        # ── Priority coverage ──
        priorities = [s.get("priority", "").lower() for s in steps]
        priority_ok = all(p.lower() in priorities for p in tc["must_have_priorities"])

        # ── Priority ordering (immediate before short-term before long-term) ──
        priority_order = {"immediate": 0, "short-term": 1, "short_term": 1, "long-term": 2, "long_term": 2}
        priority_vals = [priority_order.get(p, 99) for p in priorities]
        ordering_ok = priority_vals == sorted(priority_vals)

        # ── Source citation ──
        sources = [s.get("source_document", "") or s.get("source", "") for s in steps]
        all_sources_text = " ".join(str(s).lower() for s in sources)
        source_cited = tc["expected_source_contains"].lower() in all_sources_text

        # ── Command specificity / keyword check ──
        all_actions = " ".join(s.get("action", "") for s in steps).lower()
        keywords_found = [kw for kw in tc["should_contain_keywords"] if kw.lower() in all_actions]
        keyword_coverage = len(keywords_found) / len(tc["should_contain_keywords"])

        passed = count_ok and priority_ok and keyword_coverage >= 0.3
        icon = "✅ PASS" if passed else "❌ FAIL"

        print(f"\n  {icon} | {tc['name']}")
        print(f"    Steps:              {len(steps)} (min: {tc['min_steps']})")
        print(f"    Priorities:         {priorities}")
        print(f"    Ordering OK:        {ordering_ok}")
        print(f"    Source cited:        {source_cited} ({all_sources_text[:60]}...)")
        print(f"    Keywords found:     {keywords_found} / {tc['should_contain_keywords']}")
        print(f"    Keyword coverage:   {keyword_coverage:.0%}")

        results.append({
            "name": tc["name"], "agent": "remediation",
            "step_count": len(steps), "priority_ok": priority_ok,
            "ordering_ok": ordering_ok, "source_cited": source_cited,
            "keyword_coverage": round(keyword_coverage, 2), "pass": passed,
        })

    return results


# ═══════════════════════════════════════════════════════════
# MASTER RUNNER
# ═══════════════════════════════════════════════════════════

def run_all_agent_evals() -> dict:
    """Run all 4 agent evaluations and print combined scorecard."""
    settings = get_settings()
    graph, retriever, vs = build_graph(settings)

    all_results = []

    lp_results = evaluate_log_parser(graph, settings)
    all_results.extend(lp_results)

    rc_results = evaluate_root_cause(graph, settings)
    all_results.extend(rc_results)

    ce_results = evaluate_correlation(graph, settings)
    all_results.extend(ce_results)

    rm_results = evaluate_remediation(graph, settings)
    all_results.extend(rm_results)

    # ── Combined Scorecard ──
    print("\n" + "=" * 70)
    print("  AGENT-LEVEL EVALUATION SCORECARD")
    print("=" * 70)

    agents = {
        "log_parser": lp_results,
        "root_cause": rc_results,
        "correlation": ce_results,
        "remediation": rm_results,
    }

    total_pass = 0
    total_tests = 0
    for agent_name, agent_results in agents.items():
        passed = sum(1 for r in agent_results if r["pass"])
        total = len(agent_results)
        total_pass += passed
        total_tests += total
        rate = passed / total if total else 0
        icon = "✅" if rate >= 0.67 else "⚠️" if rate >= 0.33 else "❌"
        print(f"  {icon} {agent_name:25s}  {passed}/{total}  ({rate:.0%})")

    overall = total_pass / total_tests if total_tests else 0
    print(f"\n  {'=' * 50}")
    print(f"  OVERALL: {total_pass}/{total_tests} ({overall:.0%})")
    print(f"  {'=' * 50}")

    # ── Save results ──
    results_dir = Path("evaluation/results")
    results_dir.mkdir(parents=True, exist_ok=True)
    output = {
        "summary": {
            "total_pass": total_pass, "total_tests": total_tests,
            "overall_rate": round(overall, 3),
            "timestamp": datetime.now().isoformat(),
        },
        "details": all_results,
    }
    (results_dir / "agent_results.json").write_text(
        json.dumps(output, indent=2), encoding="utf-8"
    )
    print(f"\n  💾 Results saved to evaluation/results/agent_results.json")

    return output


def log_to_langsmith(results: dict) -> None:
    """Log agent evaluation results to LangSmith."""
    # try:
    #     from langsmith import Client

    #     client = Client()
    #     dataset_name = "agent-eval"

    #     try:
    #         dataset = client.create_dataset(
    #             dataset_name=dataset_name,
    #             description="Agent-level evaluation for Incident RCA Assistant",
    #         )
    #     except Exception:
    #         datasets = list(client.list_datasets(dataset_name=dataset_name))
    #         dataset = datasets[0] if datasets else None

    #     if dataset:
    #         for r in results["details"]:
    #             client.create_example(
    #                 inputs={"name": r["name"], "agent": r["agent"]},
    #                 outputs={k: v for k, v in r.items() if k not in ("name", "agent")},
    #                 dataset_id=dataset.id,
    #             )
    #         print(f"  ☁️  Logged {len(results['details'])} results to LangSmith dataset: {dataset_name}")
    # except ImportError:
    #     print("  ⚠️  langsmith not installed — skipping")
    # except Exception as e:
    #     print(f"  ⚠️  LangSmith logging failed: {e}")
    try:
        from langsmith import Client
        from langsmith.run_trees import RunTree

        client = Client()

        for r in results["details"]:
            run = RunTree(
                name=f"agent-{r['agent']}-{r['name'][:20]}",
                run_type="chain",
                inputs={"scenario": r["name"], "agent": r["agent"]},
                outputs=r,
                project_name="incident-rca-eval",
            )
            run.end(outputs=run.outputs)
            run.post()

            # ── Log metrics based on agent type ──

            if r["agent"] == "log_parser":
                client.create_feedback(
                    run_id=run.id, key="service_f1",
                    score=r.get("service_f1", 0.0),
                    comment=f"Service F1: {r.get('service_f1')}",
                )
                client.create_feedback(
                    run_id=run.id, key="timestamp_correct",
                    score=1.0 if r.get("timestamp_correct") else 0.0,
                )
                client.create_feedback(
                    run_id=run.id, key="pass",
                    score=1.0 if r.get("pass") else 0.0,
                )

            elif r["agent"] == "root_cause":
                client.create_feedback(
                    run_id=run.id, key="category_match",
                    score=1.0 if r.get("category_match") else 0.0,
                )
                client.create_feedback(
                    run_id=run.id, key="confidence_match",
                    score=1.0 if r.get("confidence_match") else 0.0,
                )
                client.create_feedback(
                    run_id=run.id, key="evidence_grounding",
                    score=1.0 if r.get("has_evidence", r.get("evidence_count", 0) > 0) else 0.0,
                )
                client.create_feedback(
                    run_id=run.id, key="keyword_coverage",
                    score=r.get("keyword_coverage", 0.0),
                )
                client.create_feedback(
                    run_id=run.id, key="pass",
                    score=1.0 if r.get("pass") else 0.0,
                )

            elif r["agent"] == "correlation":
                client.create_feedback(
                    run_id=run.id, key="service_coverage",
                    score=r.get("service_coverage", 0.0),
                )
                client.create_feedback(
                    run_id=run.id, key="scores_valid",
                    score=1.0 if r.get("scores_valid") else 0.0,
                )
                client.create_feedback(
                    run_id=run.id, key="pass",
                    score=1.0 if r.get("pass") else 0.0,
                )

            elif r["agent"] == "remediation":
                client.create_feedback(
                    run_id=run.id, key="keyword_coverage",
                    score=r.get("keyword_coverage", 0.0),
                )
                client.create_feedback(
                    run_id=run.id, key="source_cited",
                    score=1.0 if r.get("source_cited") else 0.0,
                )
                client.create_feedback(
                    run_id=run.id, key="ordering_ok",
                    score=1.0 if r.get("ordering_ok") else 0.0,
                )
                client.create_feedback(
                    run_id=run.id, key="pass",
                    score=1.0 if r.get("pass") else 0.0,
                )

        print(f"  ☁️  Logged {len(results['details'])} agent runs with scores to LangSmith project: incident-rca-eval")

    except ImportError:
        print("  ⚠️  langsmith not installed — skipping")
    except Exception as e:
        print(f"  ⚠️  LangSmith logging failed: {e}")

if __name__ == "__main__":
    results = run_all_agent_evals()
    log_to_langsmith(results)
