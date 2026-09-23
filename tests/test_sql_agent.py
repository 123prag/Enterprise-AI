"""Phase 4 tests: SQL agent safety validation + parameterized query
correctness, using the same seed data as Phase 2's tests.
"""

import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.agents.sql_agent import (  # noqa: E402
    IncidentQueryFilters,
    SQLAgent,
    SQLSafetyError,
    execute_readonly_sql,
    validate_readonly_sql,
)
from app.database import seed as seed_module  # noqa: E402
from app.database.models import Base, IncidentStatus, Severity  # noqa: E402

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
TestSession = sessionmaker(bind=engine)


def setup_module(_module):
    Base.metadata.create_all(bind=engine)
    session = TestSession()
    users = seed_module.seed_users(session, n=15)
    devices = seed_module.seed_devices(session, users)
    seed_module.seed_software_versions(session)
    seed_module.seed_system_status(session)
    seed_module.seed_incidents(session, users, devices, n=40)
    session.commit()
    session.close()


# --------------------------------------------------------------------------
# Safety validation
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE incidents",
        "DELETE FROM incidents WHERE id = 1",
        "UPDATE incidents SET status = 'closed'",
        "SELECT * FROM incidents; DROP TABLE users",
        "INSERT INTO incidents (title) VALUES ('x')",
        "SELECT * FROM secret_table",
        "",
        "   ",
    ],
)
def test_validate_readonly_sql_rejects_unsafe_statements(sql):
    with pytest.raises(SQLSafetyError):
        validate_readonly_sql(sql)


def test_validate_readonly_sql_accepts_simple_select():
    validate_readonly_sql("select * from incidents where category = :category")


def test_execute_readonly_sql_rejects_destructive_statement():
    session = TestSession()
    try:
        with pytest.raises(SQLSafetyError):
            execute_readonly_sql(session, "DELETE FROM incidents")
    finally:
        session.close()


def test_execute_readonly_sql_runs_parameterized_select():
    session = TestSession()
    try:
        rows = execute_readonly_sql(
            session,
            "select category, severity from incidents where category = :cat limit 5",
            {"cat": "VPN"},
        )
        assert all(r["category"] == "VPN" for r in rows)
    finally:
        session.close()


# --------------------------------------------------------------------------
# Structured query builder
# --------------------------------------------------------------------------


def test_search_incidents_filters_by_category():
    session = TestSession()
    try:
        agent = SQLAgent(session)
        results = agent.search_incidents(IncidentQueryFilters(category="VPN", limit=100))
        assert len(results) > 0
        assert all(r.category == "VPN" for r in results)
    finally:
        session.close()


def test_count_incidents_matches_search_length_for_small_limit():
    session = TestSession()
    try:
        agent = SQLAgent(session)
        filters = IncidentQueryFilters(category="Authentication", limit=200)
        results = agent.search_incidents(filters)
        count = agent.count_incidents(filters)
        assert count == len(results)
    finally:
        session.close()


def test_search_incidents_filters_by_severity_and_status():
    session = TestSession()
    try:
        agent = SQLAgent(session)
        results = agent.search_incidents(
            IncidentQueryFilters(severity=Severity.critical, status=IncidentStatus.resolved, limit=200)
        )
        assert all(r.severity == "critical" and r.status == "resolved" for r in results)
    finally:
        session.close()


def test_get_incident_history_for_unknown_ref_returns_empty():
    session = TestSession()
    try:
        agent = SQLAgent(session)
        assert agent.get_incident_history("INC-99999") == []
    finally:
        session.close()


def test_find_related_incidents_matches_category_and_error_code():
    session = TestSession()
    try:
        agent = SQLAgent(session)
        # find a VPN incident with a non-null error code to test against
        vpn_results = agent.search_incidents(
            IncidentQueryFilters(category="VPN", limit=200)
        )
        target = next((r for r in vpn_results if r.error_code), None)
        if target is None:
            pytest.skip("no VPN incident with an error_code in this seed sample")
        related = agent.find_related_incidents(target.incident_ref)
        assert all(r.category == "VPN" and r.error_code == target.error_code for r in related)
    finally:
        session.close()
