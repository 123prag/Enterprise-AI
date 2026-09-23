"""Ticket lifecycle tools: create_ticket, update_ticket, get_ticket.

Ticket status transitions follow the IT Service Management Policy:
open -> in_progress -> (pending_approval, if a high-risk action is
attached) -> resolved -> closed, with reopen possible within 7 days.
This module enforces that a ticket cannot be marked resolved directly
from pending_approval — it must pass through an approval decision first
(see app/database/models.HumanApproval, wired up in Phase 7).
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.database.models import Incident, Ticket, TicketStatus
from app.database.session import get_session
from app.tools.schemas import ToolOutput

logger = logging.getLogger(__name__)

_ILLEGAL_TRANSITIONS = {
    (TicketStatus.pending_approval, TicketStatus.resolved),
    (TicketStatus.closed, TicketStatus.open),
    (TicketStatus.closed, TicketStatus.in_progress),
}


def _new_ticket_ref() -> str:
    return f"TCK-{secrets.randbelow(900000) + 100000}"


# --------------------------------------------------------------------------
# create_ticket
# --------------------------------------------------------------------------


class CreateTicketInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    incident_ref: str | None = None
    priority: str = "medium"
    created_by: str = Field(min_length=1)


class CreateTicketOutput(ToolOutput):
    ticket_ref: str | None = None


def create_ticket(input: CreateTicketInput) -> CreateTicketOutput:
    try:
        with get_session() as session:
            incident_id = None
            if input.incident_ref:
                incident = session.execute(
                    select(Incident).where(Incident.incident_ref == input.incident_ref)
                ).scalar_one_or_none()
                if incident is None:
                    return CreateTicketOutput(
                        success=False,
                        error=f"Unknown incident_ref: {input.incident_ref!r}",
                    )
                incident_id = incident.id

            ticket_ref = _new_ticket_ref()
            ticket = Ticket(
                ticket_ref=ticket_ref,
                incident_id=incident_id,
                title=input.title,
                description=input.description,
                status=TicketStatus.open,
                priority=input.priority,
                created_by=input.created_by,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            session.add(ticket)

        logger.info("Created ticket %s for incident %s", ticket_ref, input.incident_ref)
        return CreateTicketOutput(ticket_ref=ticket_ref)
    except SQLAlchemyError as e:
        logger.exception("create_ticket DB error")
        return CreateTicketOutput(success=False, error=f"Database error: {e}")
    except Exception as e:  # noqa: BLE001
        logger.exception("create_ticket unexpected error")
        return CreateTicketOutput(success=False, error=str(e))


# --------------------------------------------------------------------------
# update_ticket
# --------------------------------------------------------------------------


class UpdateTicketInput(BaseModel):
    ticket_ref: str = Field(min_length=1)
    status: TicketStatus | None = None
    assigned_to: str | None = None
    note: str | None = None
    updated_by: str = Field(min_length=1)


class UpdateTicketOutput(ToolOutput):
    ticket_ref: str | None = None
    new_status: str | None = None


def update_ticket(input: UpdateTicketInput) -> UpdateTicketOutput:
    try:
        with get_session() as session:
            ticket = session.execute(
                select(Ticket).where(Ticket.ticket_ref == input.ticket_ref)
            ).scalar_one_or_none()
            if ticket is None:
                return UpdateTicketOutput(
                    success=False, error=f"Unknown ticket_ref: {input.ticket_ref!r}"
                )

            if input.status is not None:
                if (ticket.status, input.status) in _ILLEGAL_TRANSITIONS:
                    return UpdateTicketOutput(
                        success=False,
                        error=(
                            f"Illegal status transition: {ticket.status.value} -> "
                            f"{input.status.value}. A ticket pending approval must "
                            "receive an approval decision before it can be resolved."
                        ),
                    )
                ticket.status = input.status

            if input.assigned_to is not None:
                ticket.assigned_to = input.assigned_to

            ticket.updated_at = datetime.utcnow()

        logger.info(
            "Updated ticket %s by %s (status=%s)",
            input.ticket_ref,
            input.updated_by,
            input.status.value if input.status else "unchanged",
        )
        return UpdateTicketOutput(
            ticket_ref=input.ticket_ref,
            new_status=input.status.value if input.status else None,
        )
    except SQLAlchemyError as e:
        logger.exception("update_ticket DB error")
        return UpdateTicketOutput(success=False, error=f"Database error: {e}")
    except Exception as e:  # noqa: BLE001
        logger.exception("update_ticket unexpected error")
        return UpdateTicketOutput(success=False, error=str(e))


# --------------------------------------------------------------------------
# get_ticket
# --------------------------------------------------------------------------


class GetTicketInput(BaseModel):
    ticket_ref: str = Field(min_length=1)


class GetTicketOutput(ToolOutput):
    ticket_ref: str | None = None
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    assigned_to: str | None = None
    created_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    incident_ref: str | None = None


def get_ticket(input: GetTicketInput) -> GetTicketOutput:
    try:
        with get_session() as session:
            ticket = session.execute(
                select(Ticket).where(Ticket.ticket_ref == input.ticket_ref)
            ).scalar_one_or_none()
            if ticket is None:
                return GetTicketOutput(
                    success=False, error=f"Unknown ticket_ref: {input.ticket_ref!r}"
                )

            incident_ref = None
            if ticket.incident_id:
                incident = session.execute(
                    select(Incident).where(Incident.id == ticket.incident_id)
                ).scalar_one_or_none()
                incident_ref = incident.incident_ref if incident else None

            return GetTicketOutput(
                ticket_ref=ticket.ticket_ref,
                title=ticket.title,
                description=ticket.description,
                status=ticket.status.value,
                priority=ticket.priority,
                assigned_to=ticket.assigned_to,
                created_by=ticket.created_by,
                created_at=ticket.created_at,
                updated_at=ticket.updated_at,
                incident_ref=incident_ref,
            )
    except SQLAlchemyError as e:
        logger.exception("get_ticket DB error")
        return GetTicketOutput(success=False, error=f"Database error: {e}")
    except Exception as e:  # noqa: BLE001
        logger.exception("get_ticket unexpected error")
        return GetTicketOutput(success=False, error=str(e))
