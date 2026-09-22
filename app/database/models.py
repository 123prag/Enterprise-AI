"""SQLAlchemy ORM models for the incident copilot's structured data.

Tables (per project spec):
    users, devices, incidents, incident_history, documents,
    document_metadata, tickets, system_status, software_versions,
    agent_runs, tool_calls, evaluations, human_approvals

Design notes:
- Works identically against SQLite (local) and PostgreSQL (production) —
  no dialect-specific types are used.
- Timestamps are stored as naive UTC datetimes.
- Foreign keys use ON DELETE restrictions appropriate for an audit-style
  system: incident/ticket history should never silently disappear.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# --------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------


class Severity(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class IncidentStatus(str, enum.Enum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"
    closed = "closed"
    reopened = "reopened"


class TicketStatus(str, enum.Enum):
    open = "open"
    in_progress = "in_progress"
    pending_approval = "pending_approval"
    resolved = "resolved"
    closed = "closed"


class RiskLevel(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class ApprovalDecision(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    more_info_requested = "more_info_requested"


class DocumentType(str, enum.Enum):
    sop = "sop"
    guide = "guide"
    policy = "policy"
    reference = "reference"
    release_notes = "release_notes"


# --------------------------------------------------------------------------
# Core entities
# --------------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(150), unique=True)
    department: Mapped[str] = mapped_column(String(80), index=True)
    role: Mapped[str] = mapped_column(String(80))
    access_level: Mapped[str] = mapped_column(String(20), default="standard")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    devices: Mapped[list["Device"]] = relationship(back_populates="owner")
    incidents: Mapped[list["Incident"]] = relationship(back_populates="reported_by")


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_tag: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    device_type: Mapped[str] = mapped_column(String(40))  # laptop, desktop, mobile
    os_name: Mapped[str] = mapped_column(String(40))  # Windows, macOS, Linux
    os_version: Mapped[str] = mapped_column(String(40))
    vpn_client_version: Mapped[str] = mapped_column(String(40), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_managed: Mapped[bool] = mapped_column(Boolean, default=True)

    owner: Mapped["User"] = relationship(back_populates="devices")
    incidents: Mapped[list["Incident"]] = relationship(back_populates="device")


class SoftwareVersion(Base):
    __tablename__ = "software_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_name: Mapped[str] = mapped_column(String(80), index=True)
    version: Mapped[str] = mapped_column(String(40))
    release_date: Mapped[datetime] = mapped_column(DateTime)
    is_known_problematic: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, nullable=True)


class SystemStatus(Base):
    __tablename__ = "system_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_name: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(20))  # operational, degraded, outage
    region: Mapped[str] = mapped_column(String(40), default="global")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    details: Mapped[str] = mapped_column(Text, nullable=True)


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_ref: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    reported_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), nullable=True)
    category: Mapped[str] = mapped_column(String(60), index=True)  # VPN, Auth, Network...
    error_code: Mapped[str] = mapped_column(String(30), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[Severity] = mapped_column(Enum(Severity), index=True)
    status: Mapped[IncidentStatus] = mapped_column(
        Enum(IncidentStatus), default=IncidentStatus.open, index=True
    )
    department: Mapped[str] = mapped_column(String(80), index=True)
    os_name: Mapped[str] = mapped_column(String(40), nullable=True)
    software_version: Mapped[str] = mapped_column(String(40), nullable=True)
    resolution: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    resolved_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    related_incident_id: Mapped[int] = mapped_column(
        ForeignKey("incidents.id"), nullable=True
    )

    reported_by: Mapped["User"] = relationship(back_populates="incidents")
    device: Mapped["Device"] = relationship(back_populates="incidents")
    history: Mapped[list["IncidentHistory"]] = relationship(back_populates="incident")
    tickets: Mapped[list["Ticket"]] = relationship(back_populates="incident")


class IncidentHistory(Base):
    """Append-only audit trail of status/field changes on an incident."""

    __tablename__ = "incident_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), index=True)
    changed_field: Mapped[str] = mapped_column(String(60))
    old_value: Mapped[str] = mapped_column(String(200), nullable=True)
    new_value: Mapped[str] = mapped_column(String(200), nullable=True)
    changed_by: Mapped[str] = mapped_column(String(120))
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    note: Mapped[str] = mapped_column(Text, nullable=True)

    incident: Mapped["Incident"] = relationship(back_populates="history")


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_ref: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[TicketStatus] = mapped_column(Enum(TicketStatus), default=TicketStatus.open)
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    assigned_to: Mapped[str] = mapped_column(String(120), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    incident: Mapped["Incident"] = relationship(back_populates="tickets")


# --------------------------------------------------------------------------
# Knowledge base / documents
# --------------------------------------------------------------------------


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_name: Mapped[str] = mapped_column(String(200))
    file_path: Mapped[str] = mapped_column(String(300))
    document_type: Mapped[DocumentType] = mapped_column(Enum(DocumentType))
    department: Mapped[str] = mapped_column(String(80), nullable=True)
    version: Mapped[str] = mapped_column(String(20), default="1.0")
    access_level: Mapped[str] = mapped_column(String(20), default="standard")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    metadata_entries: Mapped[list["DocumentMetadata"]] = relationship(
        back_populates="document"
    )


class DocumentMetadata(Base):
    """Extra key/value metadata extracted per document (or per section)."""

    __tablename__ = "document_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    section: Mapped[str] = mapped_column(String(150), nullable=True)
    key: Mapped[str] = mapped_column(String(80))
    value: Mapped[str] = mapped_column(String(300))

    document: Mapped["Document"] = relationship(back_populates="metadata_entries")


# --------------------------------------------------------------------------
# Agent execution / observability / evaluation / HITL
# --------------------------------------------------------------------------


class AgentRun(Base):
    """One row per agent invocation within a request's LangGraph run."""

    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    trace_id: Mapped[str] = mapped_column(String(64), index=True)
    agent_name: Mapped[str] = mapped_column(String(60), index=True)
    input_summary: Mapped[str] = mapped_column(Text, nullable=True)
    output_summary: Mapped[str] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=True)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, nullable=True)
    error: Mapped[str] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    agent_run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    tool_name: Mapped[str] = mapped_column(String(80), index=True)
    input_json: Mapped[str] = mapped_column(Text, nullable=True)
    output_json: Mapped[str] = mapped_column(Text, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=True)
    error: Mapped[str] = mapped_column(Text, nullable=True)
    called_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Evaluation(Base):
    """A single measured evaluation run result (never fabricated)."""

    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    dataset_name: Mapped[str] = mapped_column(String(120))
    question_id: Mapped[str] = mapped_column(String(60))
    metric_name: Mapped[str] = mapped_column(String(60), index=True)
    metric_value: Mapped[float] = mapped_column(Float)
    baseline_name: Mapped[str] = mapped_column(String(60), nullable=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    details_json: Mapped[str] = mapped_column(Text, nullable=True)


class HumanApproval(Base):
    __tablename__ = "human_approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), nullable=True)
    proposed_action: Mapped[str] = mapped_column(Text)
    risk_level: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel))
    reason: Mapped[str] = mapped_column(Text, nullable=True)
    decision: Mapped[ApprovalDecision] = mapped_column(
        Enum(ApprovalDecision), default=ApprovalDecision.pending
    )
    decided_by: Mapped[str] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    decided_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=True)
