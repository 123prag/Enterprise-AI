"""Streamlit entrypoint: the interactive incident assistant (Chat page).

Run with:
    streamlit run frontend/app.py

Requires the FastAPI backend running separately (uvicorn app.main:app).
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from api_client import APIError, post  # noqa: E402

st.set_page_config(page_title="Incident Copilot - Chat", page_icon="🛠️", layout="wide")

if "history" not in st.session_state:
    st.session_state.history = []  # list of {query, response_dict}

st.title("🛠️ Enterprise Incident Copilot")
st.caption(
    "Ask about an incident, check documented procedures, or request an action. "
    "High-risk actions are routed to human review, not executed automatically."
)

with st.sidebar:
    st.subheader("Session")
    st.write(f"{len(st.session_state.history)} message(s) this session")
    if st.button("Clear history"):
        st.session_state.history = []
        st.rerun()
    st.divider()
    st.caption(
        "Every request's `request_id` can be looked up on the **Agent Trace** "
        "page. Escalated requests appear on **Human Approval**."
    )

for turn in st.session_state.history:
    with st.chat_message("user"):
        st.write(turn["query"])
    with st.chat_message("assistant"):
        resp = turn["response"]
        if resp.get("blocked"):
            st.warning(resp["final_response"])
        elif resp.get("requires_human"):
            st.info(resp["final_response"])
            ha = resp.get("human_approval")
            if ha:
                st.caption(
                    f"Escalated - risk: **{ha['risk_level']}** - "
                    f"approval id: `{ha['approval_id']}` - status: {ha['decision']}"
                )
        else:
            st.write(resp["final_response"])
            if resp.get("citations"):
                sources = ", ".join(
                    sorted({c["document_name"] for c in resp["citations"] if c.get("document_name")})
                )
                if sources:
                    st.caption(f"Sources: {sources}")
            meta_cols = st.columns(3)
            if resp.get("category"):
                meta_cols[0].caption(f"Category: {resp['category']}")
            if resp.get("confidence") is not None:
                meta_cols[1].caption(f"Confidence: {resp['confidence']:.2f}")
            if resp.get("risk_level"):
                meta_cols[2].caption(f"Risk: {resp['risk_level']}")
        st.caption(f"request_id: `{resp.get('request_id', 'n/a')}`")

query = st.chat_input('Describe the issue, e.g. "My VPN gives error 691 after a Windows update"')
if query:
    with st.chat_message("user"):
        st.write(query)
    with st.chat_message("assistant"):
        with st.spinner("Working..."):
            try:
                response = post("/chat", {"query": query})
            except APIError as e:
                st.error(f"Backend error ({e.status_code}): {e.detail}")
                response = None
            except Exception as e:  # noqa: BLE001
                st.error(
                    f"Could not reach the backend at the configured API_BASE_URL. "
                    f"Is `uvicorn app.main:app` running? ({e})"
                )
                response = None

        if response:
            if response.get("blocked"):
                st.warning(response["final_response"])
            elif response.get("requires_human"):
                st.info(response["final_response"])
            else:
                st.write(response["final_response"])
            st.caption(f"request_id: `{response['request_id']}`")
            st.session_state.history.append({"query": query, "response": response})
