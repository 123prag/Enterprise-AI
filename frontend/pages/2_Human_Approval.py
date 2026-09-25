"""Human Approval page: lists pending high-risk actions escalated by the
graph and lets a human Approve, Reject, or Request More Information.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from api_client import APIError, get, post  # noqa: E402

st.set_page_config(page_title="Incident Copilot - Human Approval", page_icon="✅", layout="wide")
st.title("✅ Human Approval Queue")
st.caption(
    "Every action here was blocked from automatic execution by policy. "
    "Nothing is executed on approval either -- approving records the "
    "decision so a human operator can carry out the action themselves."
)

reviewer = st.text_input("Your name / id (recorded as decided_by)", value="", placeholder="e.g. alice")

try:
    approvals = get("/pending-approvals")
except APIError as e:
    st.error(f"Could not load pending approvals: {e.detail}")
    approvals = []
except Exception as e:  # noqa: BLE001
    st.error(f"Could not reach the backend: {e}")
    approvals = []

if not approvals:
    st.success("No pending approvals.")
else:
    for approval in approvals:
        with st.container(border=True):
            risk = approval["risk_level"]
            risk_color = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(risk, "⚪")
            st.markdown(f"**{risk_color} [{risk.upper()}]** {approval['proposed_action']}")
            st.caption(
                f"approval_id: `{approval['approval_id']}` - "
                f"request_id: `{approval['request_id']}` - "
                f"requested: {approval['created_at']}"
            )
            if approval.get("reason"):
                st.write(f"Reason: {approval['reason']}")

            notes = st.text_input(
                "Notes (optional)",
                key=f"notes_{approval['approval_id']}",
                label_visibility="collapsed",
                placeholder="Optional notes for this decision",
            )

            c1, c2, c3 = st.columns(3)
            disabled = not reviewer.strip()
            if disabled:
                st.caption("Enter your name above to enable decisions.")

            def _decide(endpoint: str, approval_id: int, success_message: str) -> None:
                try:
                    post(endpoint, {"approval_id": approval_id, "decided_by": reviewer, "notes": notes or None})
                    st.success(success_message)
                    st.rerun()
                except APIError as e:
                    st.error(e.detail)

            if c1.button("✅ Approve", key=f"approve_{approval['approval_id']}", disabled=disabled):
                _decide("/approve-action", approval["approval_id"], "Approved.")

            if c2.button("❌ Reject", key=f"reject_{approval['approval_id']}", disabled=disabled):
                _decide("/reject-action", approval["approval_id"], "Rejected.")

            if c3.button("❓ Request more info", key=f"moreinfo_{approval['approval_id']}", disabled=disabled):
                _decide("/request-more-info", approval["approval_id"], "Marked as needing more information.")
