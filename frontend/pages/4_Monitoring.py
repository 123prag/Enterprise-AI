"""Monitoring page: requests, errors, latency, tool usage, escalations.

Backed entirely by /metrics (real, queried counts). Per-agent (router/
RAG/SQL/diagnosis/validation) breakdowns require the agent_runs table to
actually be populated, which is Phase 11 observability instrumentation --
this page shows tool-level and approval-level monitoring today, which is
real, and says plainly what's still missing rather than inventing it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from api_client import APIError, get  # noqa: E402

st.set_page_config(page_title="Incident Copilot - Monitoring", page_icon="📈", layout="wide")
st.title("📈 Monitoring")

try:
    metrics = get("/metrics")
except APIError as e:
    st.error(f"Could not load metrics: {e.detail}")
    metrics = None
except Exception as e:  # noqa: BLE001
    st.error(f"Could not reach the backend: {e}")
    metrics = None

if metrics:
    row1 = st.columns(4)
    row1[0].metric("Total tool calls", metrics["total_tool_calls"])
    row1[1].metric("Tool error rate", f"{metrics['tool_call_error_rate']:.1%}")
    avg_latency = metrics["avg_tool_call_latency_ms"]
    row1[2].metric("Avg tool latency", f"{avg_latency:.0f} ms" if avg_latency is not None else "n/a")
    row1[3].metric("Pending approvals", metrics["pending_human_approvals"])

    row2 = st.columns(2)
    row2[0].metric("Total human approvals (all time)", metrics["total_human_approvals"])
    row2[1].metric(
        "Escalation share",
        f"{(metrics['pending_human_approvals'] / metrics['total_human_approvals']):.1%}"
        if metrics["total_human_approvals"]
        else "n/a",
    )

    st.divider()
    st.subheader("Tool usage")
    if metrics["tool_usage"]:
        df = pd.DataFrame(
            sorted(metrics["tool_usage"].items(), key=lambda kv: -kv[1]),
            columns=["tool_name", "call_count"],
        )
        st.bar_chart(df.set_index("tool_name"))
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No tool calls recorded yet -- use the Chat page to generate some traffic.")

    st.divider()
    st.subheader("Not yet available")
    st.caption(
        "Per-agent execution counts and latency (router/RAG/SQL/diagnosis/"
        "validation individually, as opposed to tool calls) require the "
        "`agent_runs` table to be populated, which is Phase 11 observability "
        "instrumentation. Cost/token tracking is also part of that phase."
    )
    if metrics["total_agent_runs"] == 0:
        st.warning("agent_runs: 0 records -- not yet instrumented (Phase 11).")
