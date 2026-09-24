"""FastAPI routes.

The graph executes through ``app.graph.runner.run_graph`` (the
dependency-free runner from Phase 5-7) rather than the LangGraph
``StateGraph`` in ``app.graph.workflow`` -- both implement the identical
state machine over the identical node functions, but the runner has no
extra runtime dependency beyond what the tools/RAG pipeline already need,
which keeps the API deployable even in environments where standing up
the full LangGraph runtime isn't the goal. ``app.graph.workflow.build_graph()``
remains available for LangGraph-native deployment/visualization.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.tool_agent import dispatch
from app.api.schemas import (
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
    ChatRequest,
    ChatResponse,
    CitationOut,
    EvaluateRequest,
    HumanApprovalOut,
    IncidentCreateRequest,
    IncidentCreateResponse,
    IncidentDetailResponse,
    MetricsResponse,
    SearchRequest,
    SearchResponse,
)
from app.config import get_settings
from app.database.models import AgentRun, ApprovalDecision, Evaluation, HumanApproval, Incident, ToolCall, User
from app.database.session import get_db
from app.graph.deps import default_deps
from app.graph.runner import run_graph
from app.guardrails.security import AuthContext, RateLimiter, authenticate_bearer_token

router = APIRouter()
settings = get_settings()

_rate_limiter = RateLimiter(max_requests=settings.api_rate_limit_per_minute, window_seconds=60)


def get_auth(authorization: str | None = Header(default=None)) -> AuthContext:
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    ctx = authenticate_bearer_token(token, settings.api_auth_token)
    if not ctx.authenticated:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing credentials.")
    return ctx


def enforce_rate_limit(auth: AuthContext = Depends(get_auth)) -> None:
    key = auth.user_id or "anonymous"
    if not _rate_limiter.allow(key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please slow down.",
        )


# --------------------------------------------------------------------------
# /chat
# --------------------------------------------------------------------------


@router.post("/chat", response_model=ChatResponse, tags=["chat"])
def chat(body: ChatRequest, _rl: None = Depends(enforce_rate_limit)) -> ChatResponse:
    request_id = str(uuid.uuid4())
    deps = default_deps()

    state = run_graph(
        body.query,
        deps=deps,
        request_id=request_id,
        user_access_level=body.user_access_level,
    )

    human_approval = state.get("human_approval")

    return ChatResponse(
        request_id=request_id,
        final_response=state.get("final_response", ""),
        blocked=state.get("blocked", False),
        category=state.get("classification", {}).get("category"),
        confidence=state.get("confidence"),
        risk_level=state.get("risk_level"),
        requires_human=bool(human_approval),
        citations=[
            CitationOut(
                marker=c.get("marker", ""),
                document_id=c.get("document_id", ""),
                document_name=c.get("document_name", ""),
                section=c.get("section"),
            )
            for c in state.get("retrieved_documents", [])
        ],
        human_approval=(
            HumanApprovalOut(
                approval_id=human_approval.get("approval_id"),
                risk_level=human_approval.get("risk_level", "medium"),
                reason=human_approval.get("reason", ""),
                decision=human_approval.get("decision", "pending"),
            )
            if human_approval
            else None
        ),
    )


# --------------------------------------------------------------------------
# /incidents
# --------------------------------------------------------------------------


@router.post(
    "/incidents",
    response_model=IncidentCreateResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["incidents"],
)
def create_incident(body: IncidentCreateRequest, db: Session = Depends(get_db)) -> IncidentCreateResponse:
    reporter = db.execute(
        select(User).where(User.employee_id == body.reported_by_employee_id)
    ).scalar_one_or_none()
    if reporter is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No user found with employee_id {body.reported_by_employee_id!r}",
        )

    incident_ref = f"INC-{uuid.uuid4().int % 90000 + 10000}"
    incident = Incident(
        incident_ref=incident_ref,
        reported_by_id=reporter.id,
        category=body.category,
        title=body.title,
        description=body.description,
        severity=body.severity,
        department=body.department,
    )
    db.add(incident)
    db.commit()

    return IncidentCreateResponse(incident_ref=incident_ref)


@router.get("/incidents/{incident_ref}", response_model=IncidentDetailResponse, tags=["incidents"])
def get_incident(incident_ref: str, db: Session = Depends(get_db)) -> IncidentDetailResponse:
    incident = db.execute(
        select(Incident).where(Incident.incident_ref == incident_ref)
    ).scalar_one_or_none()
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown incident_ref: {incident_ref!r}"
        )

    history_result = dispatch("get_incident_history", {"incident_ref": incident_ref})

    return IncidentDetailResponse(
        incident_ref=incident.incident_ref,
        title=incident.title,
        description=incident.description,
        category=incident.category,
        error_code=incident.error_code,
        severity=incident.severity.value,
        status=incident.status.value,
        department=incident.department,
        os_name=incident.os_name,
        software_version=incident.software_version,
        resolution=incident.resolution,
        created_at=incident.created_at,
        resolved_at=incident.resolved_at,
        history=history_result.get("history", []),
    )


# --------------------------------------------------------------------------
# /search
# --------------------------------------------------------------------------


@router.post("/search", response_model=SearchResponse, tags=["search"])
def search(body: SearchRequest) -> SearchResponse:
    kb_result = dispatch(
        "search_knowledge_base",
        {
            "query": body.query,
            "top_k": body.top_k,
            "department": body.department,
            "user_access_level": body.user_access_level,
        },
    )

    related_incidents: list[dict] = []
    if body.include_incidents:
        inc_result = dispatch("search_incidents", {"limit": body.top_k})
        if inc_result.get("success", True):
            related_incidents = inc_result.get("incidents", [])

    return SearchResponse(
        answer=kb_result.get("answer"),
        citations=[
            CitationOut(
                marker=c.get("marker", ""),
                document_id=c.get("document_id", ""),
                document_name=c.get("document_name", ""),
                section=c.get("section"),
            )
            for c in kb_result.get("citations", [])
        ],
        related_incidents=related_incidents,
    )


# --------------------------------------------------------------------------
# /approve-action, /reject-action
# --------------------------------------------------------------------------


@router.post("/approve-action", response_model=ApprovalDecisionResponse, tags=["approvals"])
def approve_action_route(body: ApprovalDecisionRequest) -> ApprovalDecisionResponse:
    result = dispatch(
        "approve_action",
        {"approval_id": body.approval_id, "decided_by": body.decided_by, "notes": body.notes},
    )
    if not result.get("success", True):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("error"))
    return ApprovalDecisionResponse(approval_id=body.approval_id, decision=result["decision"])


@router.post("/reject-action", response_model=ApprovalDecisionResponse, tags=["approvals"])
def reject_action_route(body: ApprovalDecisionRequest) -> ApprovalDecisionResponse:
    result = dispatch(
        "reject_action",
        {"approval_id": body.approval_id, "decided_by": body.decided_by, "notes": body.notes},
    )
    if not result.get("success", True):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("error"))
    return ApprovalDecisionResponse(approval_id=body.approval_id, decision=result["decision"])


# --------------------------------------------------------------------------
# /metrics
# --------------------------------------------------------------------------


@router.get("/metrics", response_model=MetricsResponse, tags=["system"])
def metrics(db: Session = Depends(get_db)) -> MetricsResponse:
    total_agent_runs = db.execute(select(func.count()).select_from(AgentRun)).scalar_one()
    total_tool_calls = db.execute(select(func.count()).select_from(ToolCall)).scalar_one()
    failed_tool_calls = db.execute(
        select(func.count()).select_from(ToolCall).where(ToolCall.success.is_(False))
    ).scalar_one()
    avg_latency = db.execute(select(func.avg(ToolCall.latency_ms))).scalar_one()
    total_approvals = db.execute(select(func.count()).select_from(HumanApproval)).scalar_one()
    pending_approvals = db.execute(
        select(func.count()).select_from(HumanApproval).where(HumanApproval.decision == ApprovalDecision.pending)
    ).scalar_one()
    total_evaluations = db.execute(select(func.count()).select_from(Evaluation)).scalar_one()

    error_rate = (failed_tool_calls / total_tool_calls) if total_tool_calls else 0.0

    return MetricsResponse(
        total_agent_runs=total_agent_runs,
        total_tool_calls=total_tool_calls,
        tool_call_error_rate=round(error_rate, 4),
        avg_tool_call_latency_ms=round(avg_latency, 2) if avg_latency is not None else None,
        total_human_approvals=total_approvals,
        pending_human_approvals=pending_approvals,
        total_evaluations=total_evaluations,
    )


# --------------------------------------------------------------------------
# /evaluate
# --------------------------------------------------------------------------


@router.post("/evaluate", tags=["evaluation"])
def evaluate(body: EvaluateRequest):
    """The evaluation framework (retrieval/generation metrics, baseline
    comparisons) is built out in Phase 10. This endpoint exists now so the
    API surface is complete per spec, but honestly reports that it isn't
    implemented yet rather than returning fabricated metrics.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            f"Evaluation for dataset {body.dataset_name!r} is not yet available. "
            "The evaluation framework is implemented in Phase 10."
        ),
    )
