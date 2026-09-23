"""Phase 4 tests: individual tool behavior (validation, error handling)
and the tool agent's dispatch/logging layer.
"""

import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest  # noqa: E402
from pydantic import ValidationError  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

import app.database.session as db_session_module  # noqa: E402
from app.database import seed as seed_module  # noqa: E402
from app.database.models import Base  # noqa: E402
from app.tools.incidents import (  # noqa: E402
    CalculatePriorityInput,
    SearchIncidentsInput,
    calculate_priority,
    search_incidents,
)
from app.tools.system import (  # noqa: E402
    CheckSoftwareVersionInput,
    CheckSystemStatusInput,
    check_software_version,
    check_system_status,
)
from app.tools.tickets import (  # noqa: E402
    CreateTicketInput,
    GetTicketInput,
    UpdateTicketInput,
    create_ticket,
    get_ticket,
    update_ticket,
)

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(bind=engine)


def setup_module(_module):
    # Point the tools (which use app.database.session.get_session) at this
    # test engine/session instead of the real local.db.
    Base.metadata.create_all(bind=engine)
    db_session_module.SessionLocal = TestSessionLocal

    session = TestSessionLocal()
    users = seed_module.seed_users(session, n=15)
    devices = seed_module.seed_devices(session, users)
    seed_module.seed_software_versions(session)
    seed_module.seed_system_status(session)
    incidents = seed_module.seed_incidents(session, users, devices, n=30)
    seed_module.seed_tickets(session, incidents)
    session.commit()
    session.close()


# --------------------------------------------------------------------------
# search_incidents / calculate_priority
# --------------------------------------------------------------------------


def test_search_incidents_tool_returns_typed_output():
    output = search_incidents(SearchIncidentsInput(category="VPN", limit=10))
    assert output.success
    assert all(inc.category == "VPN" for inc in output.incidents)


def test_calculate_priority_scales_with_risk_factors():
    from app.database.models import Severity

    low_risk = calculate_priority(
        CalculatePriorityInput(severity=Severity.low, affected_users_count=1)
    )
    high_risk = calculate_priority(
        CalculatePriorityInput(
            severity=Severity.high,
            affected_users_count=5,
            is_known_problematic_version=True,
            department_is_critical=True,
        )
    )
    assert low_risk.success and high_risk.success
    assert high_risk.score > low_risk.score
    assert high_risk.priority in ("high", "critical")
    assert low_risk.priority in ("low", "medium")


def test_calculate_priority_input_validation_rejects_bad_enum():
    from app.database.models import Severity

    with pytest.raises(ValidationError):
        CalculatePriorityInput(severity="not-a-real-severity")
    # sanity: a real enum value still works
    assert CalculatePriorityInput(severity=Severity.low).severity == Severity.low


# --------------------------------------------------------------------------
# system tools
# --------------------------------------------------------------------------


def test_check_system_status_all_services():
    output = check_system_status(CheckSystemStatusInput())
    assert output.success
    assert len(output.services) >= 1


def test_check_system_status_unknown_service_fails_gracefully():
    output = check_system_status(CheckSystemStatusInput(service_name="Nonexistent Service"))
    assert not output.success
    assert "Unknown service" in output.error


def test_check_software_version_known_bad_pairing():
    output = check_software_version(
        CheckSoftwareVersionInput(product_name="CorpVPN Client", version="4.12.1")
    )
    assert output.success
    assert output.is_known_problematic is True


def test_check_software_version_unknown_version_fails_gracefully():
    output = check_software_version(
        CheckSoftwareVersionInput(product_name="CorpVPN Client", version="99.99.99")
    )
    assert not output.success
    assert output.latest_version is not None  # still reports the latest known version


# --------------------------------------------------------------------------
# ticket lifecycle
# --------------------------------------------------------------------------


def test_create_get_update_ticket_lifecycle():
    created = create_ticket(
        CreateTicketInput(
            title="Test ticket",
            description="Investigate VPN issue",
            created_by="tester",
        )
    )
    assert created.success and created.ticket_ref

    fetched = get_ticket(GetTicketInput(ticket_ref=created.ticket_ref))
    assert fetched.success
    assert fetched.title == "Test ticket"
    assert fetched.status == "open"

    from app.database.models import TicketStatus

    updated = update_ticket(
        UpdateTicketInput(
            ticket_ref=created.ticket_ref,
            status=TicketStatus.in_progress,
            updated_by="tester",
        )
    )
    assert updated.success
    assert updated.new_status == "in_progress"


def test_update_ticket_rejects_illegal_transition():
    from app.database.models import TicketStatus

    created = create_ticket(
        CreateTicketInput(title="T2", description="d", created_by="tester")
    )
    update_ticket(
        UpdateTicketInput(
            ticket_ref=created.ticket_ref,
            status=TicketStatus.pending_approval,
            updated_by="tester",
        )
    )
    result = update_ticket(
        UpdateTicketInput(
            ticket_ref=created.ticket_ref,
            status=TicketStatus.resolved,
            updated_by="tester",
        )
    )
    assert not result.success
    assert "Illegal status transition" in result.error


def test_create_ticket_unknown_incident_ref_fails():
    result = create_ticket(
        CreateTicketInput(
            title="Bad link",
            description="d",
            incident_ref="INC-DOES-NOT-EXIST",
            created_by="tester",
        )
    )
    assert not result.success


# --------------------------------------------------------------------------
# tool agent dispatch
# --------------------------------------------------------------------------


def test_tool_agent_dispatch_unknown_tool_raises():
    from app.agents.tool_agent import ToolDispatchError, dispatch

    with pytest.raises(ToolDispatchError):
        dispatch("not_a_real_tool", {})


def test_tool_agent_dispatch_invalid_input_raises():
    from app.agents.tool_agent import ToolDispatchError, dispatch

    with pytest.raises(ToolDispatchError):
        dispatch("calculate_priority", {"severity": "not-real"})


def test_tool_agent_dispatch_success_returns_dict_and_logs_call():
    from sqlalchemy import select

    from app.agents.tool_agent import dispatch
    from app.database.models import ToolCall as ToolCallRow

    result = dispatch("check_system_status", {})
    assert isinstance(result, dict)
    assert result["success"] is True

    session = TestSessionLocal()
    try:
        logged = session.execute(
            select(ToolCallRow).where(ToolCallRow.tool_name == "check_system_status")
        ).scalars().all()
        assert len(logged) >= 1
    finally:
        session.close()
