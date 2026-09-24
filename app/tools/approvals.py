"""Human-in-the-loop approval tools: request_human_approval,
approve_action, reject_action, request_more_information, get_pending_approvals.

Backed by the ``human_approvals`` table (Phase 2 schema). This is what
the graph's ``human_review`` node calls to create a durable, auditable
approval record instead of just returning an escalation message -- and
what the Streamlit human-approval page (Phase 9) will call to act on it.
"""

from __future__ import annotations

import logging
from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.database.models import ApprovalDecision, HumanApproval, Incident, RiskLevel
from app.database.session import get_session
from app.tools.schemas import ToolOutput

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# request_human_approval
# --------------------------------------------------------------------------


class RequestHumanApprovalInput(BaseModel):
    request_id: str = Field(min_length=1)
    incident_ref: str | None = None
    proposed_action: str = Field(min_length=1)
    risk_level: RiskLevel
    reason: str | None = None


class RequestHumanApprovalOutput(ToolOutput):
    approval_id: int | None = None


def request_human_approval(input: RequestHumanApprovalInput) -> RequestHumanApprovalOutput:
    try:
        with get_session() as session:
            incident_id = None
            if input.incident_ref:
                incident = session.execute(
                    select(Incident).where(Incident.incident_ref == input.incident_ref)
                ).scalar_one_or_none()
                incident_id = incident.id if incident else None

            approval = HumanApproval(
                request_id=input.request_id,
                incident_id=incident_id,
                proposed_action=input.proposed_action,
                risk_level=input.risk_level,
                reason=input.reason,
                decision=ApprovalDecision.pending,
                created_at=datetime.utcnow(),
            )
            session.add(approval)
            session.flush()
            approval_id = approval.id

        logger.info("Created human approval request %s (risk=%s)", approval_id, input.risk_level.value)
        return RequestHumanApprovalOutput(approval_id=approval_id)
    except SQLAlchemyError as e:
        logger.exception("request_human_approval DB error")
        return RequestHumanApprovalOutput(success=False, error=f"Database error: {e}")
    except Exception as e:  # noqa: BLE001
        logger.exception("request_human_approval unexpected error")
        return RequestHumanApprovalOutput(success=False, error=str(e))


# --------------------------------------------------------------------------
# approve_action / reject_action / request_more_information
# --------------------------------------------------------------------------


class DecideApprovalInput(BaseModel):
    approval_id: int
    decided_by: str = Field(min_length=1)
    notes: str | None = None


class DecideApprovalOutput(ToolOutput):
    approval_id: int | None = None
    decision: str | None = None


def _decide(input: DecideApprovalInput, decision: ApprovalDecision) -> DecideApprovalOutput:
    try:
        with get_session() as session:
            approval = session.execute(
                select(HumanApproval).where(HumanApproval.id == input.approval_id)
            ).scalar_one_or_none()
            if approval is None:
                return DecideApprovalOutput(
                    success=False, error=f"Unknown approval_id: {input.approval_id}"
                )
            if approval.decision != ApprovalDecision.pending:
                return DecideApprovalOutput(
                    success=False,
                    error=(
                        f"Approval {input.approval_id} was already decided "
                        f"({approval.decision.value}) -- decisions cannot be changed."
                    ),
                )

            approval.decision = decision
            approval.decided_by = input.decided_by
            approval.decided_at = datetime.utcnow()
            if input.notes:
                approval.notes = input.notes

        logger.info(
            "Approval %s decided as %s by %s", input.approval_id, decision.value, input.decided_by
        )
        return DecideApprovalOutput(approval_id=input.approval_id, decision=decision.value)
    except SQLAlchemyError as e:
        logger.exception("decide approval DB error")
        return DecideApprovalOutput(success=False, error=f"Database error: {e}")
    except Exception as e:  # noqa: BLE001
        logger.exception("decide approval unexpected error")
        return DecideApprovalOutput(success=False, error=str(e))


def approve_action(input: DecideApprovalInput) -> DecideApprovalOutput:
    return _decide(input, ApprovalDecision.approved)


def reject_action(input: DecideApprovalInput) -> DecideApprovalOutput:
    return _decide(input, ApprovalDecision.rejected)


def request_more_information(input: DecideApprovalInput) -> DecideApprovalOutput:
    return _decide(input, ApprovalDecision.more_info_requested)


# --------------------------------------------------------------------------
# get_pending_approvals
# --------------------------------------------------------------------------


class GetPendingApprovalsInput(BaseModel):
    limit: int = Field(default=50, ge=1, le=200)


class PendingApproval(BaseModel):
    approval_id: int
    request_id: str
    proposed_action: str
    risk_level: str
    reason: str | None
    created_at: datetime


class GetPendingApprovalsOutput(ToolOutput):
    approvals: list[PendingApproval] = Field(default_factory=list)


def get_pending_approvals(input: GetPendingApprovalsInput) -> GetPendingApprovalsOutput:
    try:
        with get_session() as session:
            rows = session.execute(
                select(HumanApproval)
                .where(HumanApproval.decision == ApprovalDecision.pending)
                .order_by(HumanApproval.created_at)
                .limit(input.limit)
            ).scalars().all()

        return GetPendingApprovalsOutput(
            approvals=[
                PendingApproval(
                    approval_id=r.id,
                    request_id=r.request_id,
                    proposed_action=r.proposed_action,
                    risk_level=r.risk_level.value,
                    reason=r.reason,
                    created_at=r.created_at,
                )
                for r in rows
            ]
        )
    except SQLAlchemyError as e:
        logger.exception("get_pending_approvals DB error")
        return GetPendingApprovalsOutput(success=False, error=f"Database error: {e}")
    except Exception as e:  # noqa: BLE001
        logger.exception("get_pending_approvals unexpected error")
        return GetPendingApprovalsOutput(success=False, error=str(e))
