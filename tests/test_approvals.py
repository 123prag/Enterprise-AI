"""Phase 7 tests: human approval tool lifecycle (request -> approve/
reject/request-more-info), and that a decided approval can't be
re-decided.
"""

import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

import app.database.session as db_session_module  # noqa: E402
from app.database.models import Base, RiskLevel  # noqa: E402
from app.tools.approvals import (  # noqa: E402
    DecideApprovalInput,
    GetPendingApprovalsInput,
    RequestHumanApprovalInput,
    approve_action,
    get_pending_approvals,
    reject_action,
    request_human_approval,
    request_more_information,
)

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(bind=engine)


def setup_module(_module):
    Base.metadata.create_all(bind=engine)
    db_session_module.SessionLocal = TestSessionLocal


def test_request_then_pending_list_then_approve():
    created = request_human_approval(
        RequestHumanApprovalInput(
            request_id="req-1",
            proposed_action="Change the production VPN configuration.",
            risk_level=RiskLevel.high,
            reason="matched high-risk pattern",
        )
    )
    assert created.success and created.approval_id is not None

    pending = get_pending_approvals(GetPendingApprovalsInput())
    assert any(a.approval_id == created.approval_id for a in pending.approvals)

    decided = approve_action(
        DecideApprovalInput(approval_id=created.approval_id, decided_by="alice", notes="looks fine")
    )
    assert decided.success
    assert decided.decision == "approved"

    pending_after = get_pending_approvals(GetPendingApprovalsInput())
    assert not any(a.approval_id == created.approval_id for a in pending_after.approvals)


def test_reject_action():
    created = request_human_approval(
        RequestHumanApprovalInput(
            request_id="req-2", proposed_action="Suspend account", risk_level=RiskLevel.high
        )
    )
    decided = reject_action(DecideApprovalInput(approval_id=created.approval_id, decided_by="bob"))
    assert decided.success
    assert decided.decision == "rejected"


def test_request_more_information():
    created = request_human_approval(
        RequestHumanApprovalInput(
            request_id="req-3", proposed_action="Delete account", risk_level=RiskLevel.high
        )
    )
    decided = request_more_information(
        DecideApprovalInput(approval_id=created.approval_id, decided_by="carol", notes="need ticket ref")
    )
    assert decided.success
    assert decided.decision == "more_info_requested"


def test_cannot_redecide_an_already_decided_approval():
    created = request_human_approval(
        RequestHumanApprovalInput(
            request_id="req-4", proposed_action="Modify firewall", risk_level=RiskLevel.high
        )
    )
    approve_action(DecideApprovalInput(approval_id=created.approval_id, decided_by="alice"))

    second = reject_action(DecideApprovalInput(approval_id=created.approval_id, decided_by="bob"))
    assert not second.success
    assert "already decided" in second.error


def test_decide_unknown_approval_id_fails_gracefully():
    result = approve_action(DecideApprovalInput(approval_id=999999, decided_by="alice"))
    assert not result.success
    assert "Unknown approval_id" in result.error
