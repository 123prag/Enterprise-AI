"""Phase 2 tests: schema creates cleanly and seed data is internally consistent.

These use an isolated in-memory SQLite database (not data/local.db) so they
never depend on or mutate the developer's local seeded database.
"""

import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import seed as seed_module  # noqa: E402
from app.database.models import Base, Document, Incident, Ticket, User  # noqa: E402

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
TestSession = sessionmaker(bind=engine)


def setup_module(_module):
    Base.metadata.create_all(bind=engine)


def test_seed_creates_expected_row_counts():
    session = TestSession()
    try:
        users = seed_module.seed_users(session, n=10)
        devices = seed_module.seed_devices(session, users)
        seed_module.seed_software_versions(session)
        seed_module.seed_system_status(session)
        incidents = seed_module.seed_incidents(session, users, devices, n=25)
        seed_module.seed_tickets(session, incidents)
        seed_module.seed_documents(session)
        session.commit()

        assert session.query(User).count() == 10
        assert session.query(Incident).count() == 25
        assert session.query(Document).count() == 15
        assert session.query(Ticket).count() > 0
    finally:
        session.close()


def test_incident_has_valid_foreign_keys():
    session = TestSession()
    try:
        incident = session.query(Incident).first()
        assert incident is not None
        assert incident.reported_by_id is not None
        reporter = session.query(User).get(incident.reported_by_id)
        assert reporter is not None
    finally:
        session.close()


def test_known_problematic_version_pairing_present():
    """The VPN 4.12.1 / Windows 24H2 regression referenced across the
    synthetic documents must actually exist in the software_versions table,
    or RAG+SQL cross-referencing in later phases would have nothing to
    validate against.
    """
    from app.database.models import SoftwareVersion

    session = TestSession()
    try:
        flagged = (
            session.query(SoftwareVersion)
            .filter_by(is_known_problematic=True)
            .all()
        )
        pairs = {(sv.product_name, sv.version) for sv in flagged}
        assert ("CorpVPN Client", "4.12.1") in pairs
        assert ("Windows", "24H2") in pairs
    finally:
        session.close()
