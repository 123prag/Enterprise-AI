"""Agent Trace page: shows the per-tool execution trace for one /chat
request_id -- timing, success/failure, tool names, in order. Only
execution metadata is shown, never hidden reasoning (none is stored
anywhere in this system to begin with).

Full per-node (router/diagnosis/validation) tracing beyond tool calls is
a Phase 11 addition; today this reflects the tool_calls table only.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from api_client import APIError, get  # noqa: E402

st.set_page_config(page_title="Incident Copilot - Agent Trace", page_icon="🔍", layout="wide")
st.title("🔍 Agent Trace")
st.caption(
    "Router -> RAG / SQL / Tools -> Diagnosis -> Validation. "
    "Shows tool execution metadata for one request; no hidden chain-of-thought is stored or displayed."
)

recent_ids = [turn["response"]["request_id"] for turn in st.session_state.get("history", [])]

col1, col2 = st.columns([3, 1])
with col1:
    default_id = recent_ids[-1] if recent_ids else ""
    request_id = st.text_input("request_id", value=default_id, placeholder="paste a request_id from Chat")
with col2:
    if recent_ids:
        picked = st.selectbox("Recent (this session)", options=list(reversed(recent_ids)))
        if st.button("Use selected"):
            request_id = picked
            st.rerun()

if request_id:
    try:
        trace = get(f"/trace/{request_id}")
    except APIError as e:
        st.error(f"Could not load trace: {e.detail}")
        trace = []
    except Exception as e:  # noqa: BLE001
        st.error(f"Could not reach the backend: {e}")
        trace = []

    if trace:
        df = pd.DataFrame(trace)
        df = df[["tool_name", "success", "latency_ms", "called_at", "error"]]
        st.dataframe(df, use_container_width=True, hide_index=True)

        total_latency = df["latency_ms"].sum()
        st.caption(
            f"{len(df)} tool call(s) - total tool latency: {total_latency:.1f} ms - "
            f"{df['success'].sum()} succeeded, {(~df['success']).sum()} failed"
        )
    else:
        st.info(
            "No tool calls recorded for this request_id yet, or it doesn't exist. "
            "A query that only needed the RAG/SQL branches with no explicit tool "
            "action may show fewer entries than expected -- only actual tool "
            "invocations are logged here."
        )
else:
    st.info("Enter or select a request_id to view its trace.")
