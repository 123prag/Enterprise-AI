"""Tool Agent: a single typed dispatch point over every tool in the system.

LangGraph nodes (Phase 5) call ``dispatch(tool_name, input_dict)`` rather
than importing individual tool functions, which keeps the graph decoupled
from tool implementations and gives one place to log every tool
invocation (latency, success, errors) into the ``tool_calls`` table for
observability (fully wired up in Phase 11 — this records timing/success
now so that later phase has real data to report on, not fabricated
numbers).
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from app.database.models import ToolCall as ToolCallRow
from app.database.session import get_session
from app.tools.incidents import (
    CalculatePriorityInput,
    GetIncidentHistoryInput,
    SearchIncidentsInput,
    calculate_priority,
    get_incident_history,
    search_incidents,
)
from app.tools.knowledge_base import SearchKnowledgeBaseInput, search_knowledge_base
from app.tools.system import (
    CheckSoftwareVersionInput,
    CheckSystemStatusInput,
    check_software_version,
    check_system_status,
)
from app.tools.tickets import (
    CreateTicketInput,
    GetTicketInput,
    UpdateTicketInput,
    create_ticket,
    get_ticket,
    update_ticket,
)

logger = logging.getLogger(__name__)


@dataclass
class ToolSpec:
    input_model: type[BaseModel]
    func: Callable[[BaseModel], BaseModel]


TOOL_REGISTRY: dict[str, ToolSpec] = {
    "search_knowledge_base": ToolSpec(SearchKnowledgeBaseInput, search_knowledge_base),
    "search_incidents": ToolSpec(SearchIncidentsInput, search_incidents),
    "get_incident_history": ToolSpec(GetIncidentHistoryInput, get_incident_history),
    "check_system_status": ToolSpec(CheckSystemStatusInput, check_system_status),
    "check_software_version": ToolSpec(CheckSoftwareVersionInput, check_software_version),
    "create_ticket": ToolSpec(CreateTicketInput, create_ticket),
    "update_ticket": ToolSpec(UpdateTicketInput, update_ticket),
    "get_ticket": ToolSpec(GetTicketInput, get_ticket),
    "calculate_priority": ToolSpec(CalculatePriorityInput, calculate_priority),
}


class ToolDispatchError(Exception):
    """Raised for unknown tool names or input validation failures — a
    distinct type from a tool's own reported failure (which comes back as
    a normal ``success=False`` output, not an exception)."""


def dispatch(
    tool_name: str,
    input_data: dict,
    request_id: str | None = None,
    agent_run_id: int | None = None,
) -> dict:
    """Validate input against the tool's schema, run it, log the call, and
    return the output as a plain dict (JSON-serializable) regardless of
    which tool ran.
    """
    if tool_name not in TOOL_REGISTRY:
        raise ToolDispatchError(
            f"Unknown tool: {tool_name!r}. Available: {sorted(TOOL_REGISTRY)}"
        )

    spec = TOOL_REGISTRY[tool_name]
    request_id = request_id or str(uuid.uuid4())

    try:
        validated_input = spec.input_model(**input_data)
    except ValidationError as e:
        raise ToolDispatchError(f"Invalid input for tool {tool_name!r}: {e}") from e

    start = time.perf_counter()
    error_text = None
    success = True
    output_dict: dict = {}

    try:
        output = spec.func(validated_input)
        output_dict = output.model_dump(mode="json")
        success = output_dict.get("success", True)
        error_text = output_dict.get("error")
    except Exception as e:  # noqa: BLE001 - tool boundary must not crash the graph
        logger.exception("Tool %s raised unexpectedly", tool_name)
        success = False
        error_text = str(e)
        output_dict = {"success": False, "error": error_text}

    latency_ms = (time.perf_counter() - start) * 1000

    _log_tool_call(
        request_id=request_id,
        agent_run_id=agent_run_id,
        tool_name=tool_name,
        input_data=input_data,
        output_dict=output_dict,
        success=success,
        latency_ms=latency_ms,
        error_text=error_text,
    )

    return output_dict


def _log_tool_call(
    request_id: str,
    agent_run_id: int | None,
    tool_name: str,
    input_data: dict,
    output_dict: dict,
    success: bool,
    latency_ms: float,
    error_text: str | None,
) -> None:
    try:
        with get_session() as session:
            session.add(
                ToolCallRow(
                    request_id=request_id,
                    agent_run_id=agent_run_id,
                    tool_name=tool_name,
                    input_json=json.dumps(input_data, default=str),
                    output_json=json.dumps(output_dict, default=str),
                    success=success,
                    latency_ms=latency_ms,
                    error=error_text,
                )
            )
    except Exception:  # noqa: BLE001 - observability must never break the tool call itself
        logger.exception("Failed to log tool_call for %s (non-fatal)", tool_name)
