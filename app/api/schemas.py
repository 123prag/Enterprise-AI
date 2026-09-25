"""Pydantic request/response schemas for the FastAPI layer.

Kept separate from the tool/agent schemas (app/tools/schemas.py,
app/agents/*) since the API's public contract is allowed to evolve
independently of internal tool signatures.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.database.models import Severity

# --------------------------------------------------------------------------
# /chat
# --------------------------------------------------------------------------


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    user_access_level: str = "standard"


class CitationOut(BaseModel):
    marker: str
    document_id: str
    document_name: str
    section: str | None = None


class HumanApprovalOut(BaseModel):
    approval_id: int | str | None = None
    risk_level: str
    reason: str
    decision: str


class ChatResponse(BaseModel):
    request_id: str
    final_response: str
    blocked: bool = False
    category: str | None = None
    confidence: float | None = None
    risk_level: str | None = None
    requires_human: bool = False
    citations: list[CitationOut] = Field(default_factory=list)
    human_approval: HumanApprovalOut | None = None


# --------------------------------------------------------------------------
# /incidents
# --------------------------------------------------------------------------


class IncidentCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    category: str = Field(min_length=1)
    severity: Severity
    department: str = Field(min_length=1)
    reported_by_employee_id: str = Field(min_length=1)
    device_asset_tag: str | None = None


class IncidentCreateResponse(BaseModel):
    incident_ref: str


class IncidentDetailResponse(BaseModel):
    incident_ref: str
    title: str
    description: str
    category: str
    error_code: str | None
    severity: str
    status: str
    department: str
    os_name: str | None
    software_version: str | None
    resolution: str | None
    created_at: datetime
    resolved_at: datetime | None
    history: list[dict] = Field(default_factory=list)


# --------------------------------------------------------------------------
# /search
# --------------------------------------------------------------------------


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    department: str | None = None
    include_incidents: bool = True
    user_access_level: str = "standard"


class SearchResponse(BaseModel):
    answer: str | None = None
    citations: list[CitationOut] = Field(default_factory=list)
    related_incidents: list[dict] = Field(default_factory=list)


# --------------------------------------------------------------------------
# /approve-action, /reject-action
# --------------------------------------------------------------------------


class ApprovalDecisionRequest(BaseModel):
    approval_id: int
    decided_by: str = Field(min_length=1)
    notes: str | None = None


class ApprovalDecisionResponse(BaseModel):
    approval_id: int
    decision: str


class PendingApprovalOut(BaseModel):
    approval_id: int
    request_id: str
    proposed_action: str
    risk_level: str
    reason: str | None
    created_at: datetime


class ToolCallTraceEntry(BaseModel):
    tool_name: str
    success: bool
    latency_ms: float | None
    called_at: datetime
    error: str | None = None


# --------------------------------------------------------------------------
# /metrics
# --------------------------------------------------------------------------


class MetricsResponse(BaseModel):
    total_agent_runs: int
    total_tool_calls: int
    tool_call_error_rate: float
    avg_tool_call_latency_ms: float | None
    total_human_approvals: int
    pending_human_approvals: int
    total_evaluations: int
    tool_usage: dict[str, int] = Field(default_factory=dict)


# --------------------------------------------------------------------------
# /evaluate
# --------------------------------------------------------------------------


class EvaluateRequest(BaseModel):
    dataset_name: str = Field(min_length=1)
