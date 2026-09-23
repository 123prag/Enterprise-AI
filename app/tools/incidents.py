"""Incident-related tools: search_incidents, get_incident_history,
calculate_priority.

Every tool: typed input/output, validation via Pydantic, error handling
(DB errors never propagate as raw exceptions to the caller), and logging.
"""

from __future__ import annotations

import logging
from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from app.agents.sql_agent import IncidentQueryFilters, IncidentRecord, SQLAgent
from app.database.models import IncidentStatus, Severity
from app.database.session import get_session
from app.tools.schemas import ToolOutput

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# search_incidents
# --------------------------------------------------------------------------


class SearchIncidentsInput(BaseModel):
    category: str | None = None
    error_code: str | None = None
    department: str | None = None
    os_name: str | None = None
    software_version: str | None = None
    severity: Severity | None = None
    status: IncidentStatus | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    limit: int = Field(default=20, ge=1, le=200)


class SearchIncidentsOutput(ToolOutput):
    incidents: list[IncidentRecord] = Field(default_factory=list)
    total_count: int = 0


def search_incidents(input: SearchIncidentsInput) -> SearchIncidentsOutput:
    try:
        filters = IncidentQueryFilters(**input.model_dump())
        with get_session() as session:
            agent = SQLAgent(session)
            records = agent.search_incidents(filters)
            total = agent.count_incidents(filters)
        return SearchIncidentsOutput(incidents=records, total_count=total)
    except SQLAlchemyError as e:
        logger.exception("search_incidents DB error")
        return SearchIncidentsOutput(success=False, error=f"Database error: {e}")
    except Exception as e:  # noqa: BLE001 - tool boundary: never raise to caller
        logger.exception("search_incidents unexpected error")
        return SearchIncidentsOutput(success=False, error=str(e))


# --------------------------------------------------------------------------
# get_incident_history
# --------------------------------------------------------------------------


class GetIncidentHistoryInput(BaseModel):
    incident_ref: str = Field(min_length=1, max_length=20)


class HistoryEntry(BaseModel):
    changed_field: str
    old_value: str | None
    new_value: str | None
    changed_by: str
    changed_at: datetime
    note: str | None


class GetIncidentHistoryOutput(ToolOutput):
    incident_ref: str | None = None
    history: list[HistoryEntry] = Field(default_factory=list)
    related_incidents: list[IncidentRecord] = Field(default_factory=list)


def get_incident_history(input: GetIncidentHistoryInput) -> GetIncidentHistoryOutput:
    try:
        with get_session() as session:
            agent = SQLAgent(session)
            history = agent.get_incident_history(input.incident_ref)
            related = agent.find_related_incidents(input.incident_ref)
        if not history and not related:
            return GetIncidentHistoryOutput(
                success=False,
                error=f"No incident found with ref {input.incident_ref!r}",
            )
        return GetIncidentHistoryOutput(
            incident_ref=input.incident_ref,
            history=[HistoryEntry(**h) for h in history],
            related_incidents=related,
        )
    except SQLAlchemyError as e:
        logger.exception("get_incident_history DB error")
        return GetIncidentHistoryOutput(success=False, error=f"Database error: {e}")
    except Exception as e:  # noqa: BLE001
        logger.exception("get_incident_history unexpected error")
        return GetIncidentHistoryOutput(success=False, error=str(e))


# --------------------------------------------------------------------------
# calculate_priority
# --------------------------------------------------------------------------

_SEVERITY_WEIGHT = {
    Severity.low: 1,
    Severity.medium: 2,
    Severity.high: 3,
    Severity.critical: 4,
}


class CalculatePriorityInput(BaseModel):
    severity: Severity
    affected_users_count: int = Field(default=1, ge=1)
    is_known_problematic_version: bool = False
    department_is_critical: bool = False


class CalculatePriorityOutput(ToolOutput):
    priority: str = "medium"
    score: float = 0.0
    rationale: str = ""


def calculate_priority(input: CalculatePriorityInput) -> CalculatePriorityOutput:
    """Deterministic, explainable priority scoring — not an LLM judgment
    call, so it is fast, free, and auditable. Escalation-worthy factors
    (multi-user impact, known-bad software version, critical department)
    each add weight on top of the base severity weight.
    """
    try:
        score = float(_SEVERITY_WEIGHT[input.severity])
        reasons = [f"base severity '{input.severity.value}' = {score}"]

        if input.affected_users_count >= 3:
            score += 1.5
            reasons.append(f"{input.affected_users_count} users affected (+1.5)")

        if input.is_known_problematic_version:
            score += 1.0
            reasons.append("matches known-problematic software version (+1.0)")

        if input.department_is_critical:
            score += 0.5
            reasons.append("affects a business-critical department (+0.5)")

        if score >= 5.5:
            priority = "critical"
        elif score >= 4.0:
            priority = "high"
        elif score >= 2.5:
            priority = "medium"
        else:
            priority = "low"

        return CalculatePriorityOutput(
            priority=priority, score=score, rationale="; ".join(reasons)
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("calculate_priority error")
        return CalculatePriorityOutput(success=False, error=str(e))
