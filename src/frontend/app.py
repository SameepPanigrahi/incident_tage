import json
import streamlit as st
import httpx

# ── Page config ────────────────────────────────────────────────

st.set_page_config(
    page_title="AI Incident RCA Assistant",
    page_icon="🔍",
    layout="wide",
)

# ── Example incidents ──────────────────────────────────────────

EXAMPLES = {
    "Auth Service Outage (DB Pool Exhaustion)": {
        "incident_id": "INC-2026-042",
        "logs": open("mock_data/incident_logs/auth_service_outage.log").read()
            if __import__("os").path.exists("mock_data/incident_logs/auth_service_outage.log")
            else "Paste your logs here...",
        "context": "Deployment of auth-service v2.5.0 occurred 30 minutes before the outage.",
    },
    "Payment Latency Spike (Memory Leak)": {
        "incident_id": "INC-2026-043",
        "logs": open("mock_data/incident_logs/payment_latency_spike.log").read()
            if __import__("os").path.exists("mock_data/incident_logs/payment_latency_spike.log")
            else "Paste your logs here...",
        "context": "payment-service v3.1.0 deployed 1 hour before latency increase.",
    },
    "API Gateway Timeout (Cascading Failure)": {
        "incident_id": "INC-2026-044",
        "logs": open("mock_data/incident_logs/api_gateway_timeout.log").read()
            if __import__("os").path.exists("mock_data/incident_logs/api_gateway_timeout.log")
            else "Paste your logs here...",
        "context": "No recent deployments. Inventory database migration was scheduled today.",
    },
}

# ── Colour helpers ─────────────────────────────────────────────

SEVERITY_COLORS = {
    "critical": "🔴",
    "high": "🟠",
    "medium": "🟡",
    "low": "🟢",
}

CONFIDENCE_COLORS = {
    "high": "🟢",
    "medium": "🟡",
    "low": "🔴",
}

PRIORITY_COLORS = {
    "immediate": "🔴",
    "short-term": "🟡",
    "long-term": "🟢",
}

# ── Sidebar ────────────────────────────────────────────────────

with st.sidebar:
    st.title("⚙️ Configuration")
    api_url = st.text_input("API URL", value="http://localhost:8000")
    st.divider()

    st.subheader("📂 Example Incidents")
    example_name = st.selectbox("Select an example", list(EXAMPLES.keys()))
    if st.button("Load Example"):
        ex = EXAMPLES[example_name]
        st.session_state["incident_id"] = ex["incident_id"]
        st.session_state["logs"] = ex["logs"]
        st.session_state["context"] = ex["context"]

    st.divider()
    st.caption("Built for T-Mobile Senior AI Engineer Evaluation")

# ── Main area ──────────────────────────────────────────────────

st.title("🔍 AI Incident Root Cause Assistant")
st.markdown(
    "Paste production logs below and let the multi-agent AI pipeline "
    "**summarise the incident**, **identify root causes**, "
    "**correlate anomalies**, and **recommend remediation steps**."
)

col1, col2 = st.columns([3, 1])
with col1:
    incident_id = st.text_input(
        "Incident ID",
        value=st.session_state.get("incident_id", "INC-2026-001"),
    )
with col2:
    st.metric("Pipeline", "Ready" if api_url else "No URL")

logs = st.text_area(
    "Raw Logs",
    value=st.session_state.get("logs", ""),
    height=300,
    placeholder="Paste your production logs here...",
)

additional_context = st.text_input(
    "Additional Context (optional)",
    value=st.session_state.get("context", ""),
    placeholder="e.g. Recent deployment, config change, etc.",
)

# ── Analyze button ─────────────────────────────────────────────

if st.button("🚀 Analyze Incident", type="primary", use_container_width=True):
    if not logs.strip():
        st.warning("Please paste some logs to analyze.")
    else:
        with st.spinner("🔍 Analyzing incident — running 4-agent pipeline..."):
            try:
                resp = httpx.post(
                    f"{api_url}/api/v1/analyze",
                    json={
                        "incident_id": incident_id,
                        "logs": logs,
                        "additional_context": additional_context,
                    },
                    timeout=120.0,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                st.error(f"API call failed: {exc}")
                st.stop()

        # ── Results ────────────────────────────────────────────

        st.divider()
        st.header("📊 Analysis Results")

        # Processing time
        col_a, col_b, col_c = st.columns(3)
        summary = data.get("summary", {})
        severity = summary.get("severity", "medium")
        col_a.metric("Severity", f"{SEVERITY_COLORS.get(severity, '')} {severity.upper()}")
        col_b.metric("Root Causes Found", len(data.get("root_causes", [])))
        col_c.metric("Processing Time", f"{data.get('processing_time_seconds', 0)}s")

        # ── Incident Summary ──
        st.subheader("📋 Incident Summary")
        st.markdown(f"**{summary.get('title', 'N/A')}**")
        st.write(summary.get("summary", ""))

        services = summary.get("impacted_services", [])
        if services:
            st.markdown("**Impacted Services:** " + "  ".join(
                [f"`{s}`" for s in services]
            ))

        timeline = summary.get("timeline", [])
        if timeline:
            with st.expander("📅 Timeline", expanded=False):
                for entry in timeline:
                    if isinstance(entry, dict):
                        ts = entry.get("timestamp", entry.get("label", ""))
                        ev = entry.get("event", entry.get("timestamp", ""))
                        st.markdown(f"- **{ts}** — {ev}")

        # ── Root Causes ──
        st.subheader("🔍 Root Causes")
        for rc in data.get("root_causes", []):
            conf = rc.get("confidence", "low")
            icon = CONFIDENCE_COLORS.get(conf, "")
            with st.expander(
                f"{icon} {rc.get('cause', 'Unknown')} "
                f"(Confidence: {conf.upper()}  |  Category: {rc.get('category', 'N/A')})",
                expanded=True,
            ):
                st.markdown(f"**Reasoning:** {rc.get('reasoning', '')}")
                evidence = rc.get("evidence", [])
                if evidence:
                    st.markdown("**Evidence:**")
                    for e in evidence:
                        st.markdown(f"- `{e}`")

        # ── Correlated Anomalies ──
        anomalies = data.get("correlated_anomalies", [])
        if anomalies:
            st.subheader("🔗 Correlated Anomalies")
            anomaly_table = []
            for a in anomalies:
                anomaly_table.append({
                    "Service": a.get("service", ""),
                    "Anomaly Type": a.get("anomaly_type", ""),
                    "Timestamp": a.get("timestamp", ""),
                    "Correlation Score": f"{a.get('correlation_score', 0):.2f}",
                    "Description": a.get("description", ""),
                })
            st.table(anomaly_table)

        # ── Remediation Steps ──
        steps = data.get("remediation_steps", [])
        if steps:
            st.subheader("🛠️ Remediation Steps")
            for s in steps:
                priority = s.get("priority", "long-term")
                icon = PRIORITY_COLORS.get(priority, "")
                st.markdown(
                    f"**Step {s.get('step', '?')}** {icon} `{priority.upper()}` — "
                    f"{s.get('action', '')}"
                )
                st.caption(
                    f"Impact: {s.get('estimated_impact', 'N/A')}  |  "
                    f"Source: {s.get('source_document', 'general expertise')}"
                )
