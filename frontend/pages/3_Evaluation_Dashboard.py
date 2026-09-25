"""Evaluation Dashboard: retrieval/generation/system metrics.

The evaluation framework itself (retrieval precision/recall/MRR,
groundedness, hallucination rate, baseline comparisons) is built in
Phase 10. Until then this page shows only what's actually measured
today -- system-level counts from /metrics -- and says so plainly,
rather than fabricating retrieval or generation quality numbers.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from api_client import APIError, get  # noqa: E402

st.set_page_config(page_title="Incident Copilot - Evaluation", page_icon="📊", layout="wide")
st.title("📊 Evaluation Dashboard")

try:
    metrics = get("/metrics")
except APIError as e:
    st.error(f"Could not load metrics: {e.detail}")
    metrics = None
except Exception as e:  # noqa: BLE001
    st.error(f"Could not reach the backend: {e}")
    metrics = None

if metrics:
    if metrics["total_evaluations"] == 0:
        st.warning(
            "No evaluation runs recorded yet. The retrieval/generation "
            "evaluation framework (Precision@K, Recall@K, MRR, hit rate, "
            "groundedness, faithfulness, citation correctness, hallucination "
            "rate, and baseline comparisons against no-RAG and basic-vector-RAG) "
            "is implemented in **Phase 10** and will populate this page with "
            "real, measured numbers -- nothing here is a placeholder for "
            "fabricated results."
        )
    else:
        st.metric("Total evaluation records", metrics["total_evaluations"])
        st.info(
            "Evaluation records exist, but the dashboard's breakdown by "
            "metric/dataset/baseline is built out in Phase 10."
        )

    st.divider()
    st.subheader("What's measurable today")
    cols = st.columns(3)
    cols[0].metric("Total tool calls", metrics["total_tool_calls"])
    cols[1].metric("Tool call error rate", f"{metrics['tool_call_error_rate']:.1%}")
    avg_latency = metrics["avg_tool_call_latency_ms"]
    cols[2].metric("Avg tool latency", f"{avg_latency:.0f} ms" if avg_latency is not None else "n/a")
    st.caption(
        "These are real, queried values from the tool_calls table -- see the "
        "Monitoring page for the full breakdown. They are execution metrics, "
        "not retrieval/generation quality metrics."
    )
