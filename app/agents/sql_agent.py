"""SQL Agent: turns structured (never free-form-string) filters into
parameterized SQLAlchemy queries against the incident database, and
provides a defense-in-depth raw-SQL validator for any future caller that
needs to run a validated raw statement (e.g. an LLM-generated query).

Design choice: the primary path (``SQLAgent.search_incidents`` etc.) never
builds SQL by string interpolation — it uses SQLAlchemy's expression
language with bound parameters, so it is not injectable by construction.
The optional raw-SQL path (``execute_readonly_sql``) exists to satisfy the
"generate safe SQL / validate SQL / execute read-only queries" requirement
for a future LLM-in-the-loop text-to-SQL feature, and is guarded by
:func:`validate_readonly_sql` before anything reaches the database.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.database.models import Incident, IncidentHistory, IncidentStatus, Severity

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Raw-SQL safety validation (defense in depth for any future text-to-SQL path)
# --------------------------------------------------------------------------

ALLOWED_TABLES = {
    "users",
    "devices",
    "incidents",
    "incident_history",
    "documents",
    "document_metadata",
    "tickets",
    "system_status",
    "software_versions",
    "agent_runs",
    "tool_calls",
    "evaluations",
    "human_approvals",
}

FORBIDDEN_KEYWORDS = (
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "truncate",
    "create",
    "grant",
    "revoke",
    "attach",
    "pragma",
    "exec",
    "execute",
    "--",
    ";",
)


class SQLSafetyError(ValueError):
    """Raised when a raw SQL statement fails safety validation."""


def validate_readonly_sql(sql: str) -> None:
    """Raise :class:`SQLSafetyError` unless ``sql`` is a single, read-only
    SELECT statement that only references whitelisted tables.

    This is deliberately strict rather than clever: it is much safer to
    reject a borderline-but-legitimate query than to admit a destructive
    one. Callers needing something not covered here should extend the
    structured query builder instead of relaxing this validator.
    """
    normalized = sql.strip().lower()
    if not normalized:
        raise SQLSafetyError("Empty SQL statement.")
    if not normalized.startswith("select"):
        raise SQLSafetyError("Only SELECT statements are permitted.")
    for keyword in FORBIDDEN_KEYWORDS:
        if keyword in normalized:
            raise SQLSafetyError(f"Forbidden keyword/token detected: {keyword!r}")

    referenced_tables = set(re.findall(r"\bfrom\s+([a-z_][a-z0-9_]*)", normalized))
    referenced_tables |= set(re.findall(r"\bjoin\s+([a-z_][a-z0-9_]*)", normalized))
    unknown = referenced_tables - ALLOWED_TABLES
    if unknown:
        raise SQLSafetyError(f"Query references non-whitelisted table(s): {unknown}")


def execute_readonly_sql(session: Session, sql: str, params: dict | None = None) -> list[dict]:
    """Execute a validated, parameterized read-only SQL statement.

    ``params`` must be used for any user-supplied values (never string
    formatting) — this function only adds the safety gate, it does not
    protect against injection via unparameterized string building upstream.
    """
    validate_readonly_sql(sql)
    result = session.execute(text(sql), params or {})
    return [dict(row._mapping) for row in result]


# --------------------------------------------------------------------------
# Structured, parameterized query builder (primary path)
# --------------------------------------------------------------------------


class IncidentQueryFilters(BaseModel):
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


class IncidentRecord(BaseModel):
    incident_ref: str
    category: str
    error_code: str | None
    title: str
    severity: str
    status: str
    department: str
    os_name: str | None
    software_version: str | None
    resolution: str | None
    created_at: datetime
    resolved_at: datetime | None


class SQLAgent:
    """Executes structured, parameterized incident queries. No method on
    this class accepts a free-form SQL string from a caller — the safe
    raw-SQL path lives in the module-level :func:`execute_readonly_sql`
    and is intentionally separate so it's never reached accidentally.
    """

    def __init__(self, session: Session):
        self.session = session

    def search_incidents(self, filters: IncidentQueryFilters) -> list[IncidentRecord]:
        stmt = select(Incident)

        if filters.category:
            stmt = stmt.where(Incident.category == filters.category)
        if filters.error_code:
            stmt = stmt.where(Incident.error_code == filters.error_code)
        if filters.department:
            stmt = stmt.where(Incident.department == filters.department)
        if filters.os_name:
            stmt = stmt.where(Incident.os_name == filters.os_name)
        if filters.software_version:
            stmt = stmt.where(Incident.software_version == filters.software_version)
        if filters.severity:
            stmt = stmt.where(Incident.severity == filters.severity)
        if filters.status:
            stmt = stmt.where(Incident.status == filters.status)
        if filters.created_after:
            stmt = stmt.where(Incident.created_at >= filters.created_after)
        if filters.created_before:
            stmt = stmt.where(Incident.created_at <= filters.created_before)

        stmt = stmt.order_by(Incident.created_at.desc()).limit(filters.limit)

        rows = self.session.execute(stmt).scalars().all()
        return [
            IncidentRecord(
                incident_ref=r.incident_ref,
                category=r.category,
                error_code=r.error_code,
                title=r.title,
                severity=r.severity.value if hasattr(r.severity, "value") else r.severity,
                status=r.status.value if hasattr(r.status, "value") else r.status,
                department=r.department,
                os_name=r.os_name,
                software_version=r.software_version,
                resolution=r.resolution,
                created_at=r.created_at,
                resolved_at=r.resolved_at,
            )
            for r in rows
        ]

    def count_incidents(self, filters: IncidentQueryFilters) -> int:
        """Same filters as search_incidents but returns a count, for
        queries like 'how many VPN incidents occurred after version X'."""
        from sqlalchemy import func

        stmt = select(func.count()).select_from(Incident)
        if filters.category:
            stmt = stmt.where(Incident.category == filters.category)
        if filters.error_code:
            stmt = stmt.where(Incident.error_code == filters.error_code)
        if filters.department:
            stmt = stmt.where(Incident.department == filters.department)
        if filters.os_name:
            stmt = stmt.where(Incident.os_name == filters.os_name)
        if filters.software_version:
            stmt = stmt.where(Incident.software_version == filters.software_version)
        if filters.severity:
            stmt = stmt.where(Incident.severity == filters.severity)
        if filters.status:
            stmt = stmt.where(Incident.status == filters.status)
        if filters.created_after:
            stmt = stmt.where(Incident.created_at >= filters.created_after)
        if filters.created_before:
            stmt = stmt.where(Incident.created_at <= filters.created_before)

        return self.session.execute(stmt).scalar_one()

    def get_incident_history(self, incident_ref: str) -> list[dict]:
        incident = self.session.execute(
            select(Incident).where(Incident.incident_ref == incident_ref)
        ).scalar_one_or_none()
        if incident is None:
            return []

        rows = self.session.execute(
            select(IncidentHistory)
            .where(IncidentHistory.incident_id == incident.id)
            .order_by(IncidentHistory.changed_at)
        ).scalars().all()

        return [
            {
                "changed_field": r.changed_field,
                "old_value": r.old_value,
                "new_value": r.new_value,
                "changed_by": r.changed_by,
                "changed_at": r.changed_at,
                "note": r.note,
            }
            for r in rows
        ]

    def find_related_incidents(self, incident_ref: str) -> list[IncidentRecord]:
        """Incidents explicitly linked via related_incident_id, plus other
        incidents sharing the same category+error_code (a lightweight
        recurring-issue signal without needing embeddings)."""
        incident = self.session.execute(
            select(Incident).where(Incident.incident_ref == incident_ref)
        ).scalar_one_or_none()
        if incident is None:
            return []

        stmt = select(Incident).where(
            Incident.id != incident.id,
            Incident.category == incident.category,
            Incident.error_code == incident.error_code,
        ).order_by(Incident.created_at.desc()).limit(10)

        rows = self.session.execute(stmt).scalars().all()
        return [
            IncidentRecord(
                incident_ref=r.incident_ref,
                category=r.category,
                error_code=r.error_code,
                title=r.title,
                severity=r.severity.value if hasattr(r.severity, "value") else r.severity,
                status=r.status.value if hasattr(r.status, "value") else r.status,
                department=r.department,
                os_name=r.os_name,
                software_version=r.software_version,
                resolution=r.resolution,
                created_at=r.created_at,
                resolved_at=r.resolved_at,
            )
            for r in rows
        ]
