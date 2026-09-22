"""Generate realistic synthetic enterprise data for local development,
testing, and evaluation.

Deterministic (fixed Faker/random seed) so re-running produces the same
dataset — important for reproducible evaluation baselines. Never pulls
real employee/company data; everything is fabricated.

Usage:
    python -m app.database.seed              # seed if empty
    python -m app.database.seed --reset       # drop + reseed
"""

from __future__ import annotations

import argparse
import random
from datetime import datetime, timedelta

from faker import Faker

from app.database.models import (
    Device,
    Document,
    DocumentMetadata,
    DocumentType,
    Incident,
    IncidentHistory,
    IncidentStatus,
    Severity,
    SoftwareVersion,
    SystemStatus,
    Ticket,
    TicketStatus,
    User,
)
from app.database.session import drop_db, get_session, init_db

SEED = 42
fake = Faker()
Faker.seed(SEED)
random.seed(SEED)

DEPARTMENTS = [
    "Engineering",
    "Sales",
    "Finance",
    "HR",
    "Legal",
    "Marketing",
    "Customer Support",
    "Operations",
]
ROLES = ["Engineer", "Manager", "Analyst", "Director", "Associate", "Specialist"]

OS_CHOICES = [
    ("Windows", "22H2"),
    ("Windows", "23H2"),
    ("Windows", "24H2"),
    ("macOS", "14 Sonoma"),
    ("macOS", "15 Sequoia"),
    ("Linux", "Ubuntu 22.04"),
]

VPN_CLIENT_VERSIONS = ["4.10.2", "4.11.0", "4.11.3", "4.12.1", "5.0.0"]

# Incident categories mapped to plausible error codes + titles, so the
# generated data resembles a real IT queue rather than random noise.
CATEGORY_TEMPLATES: dict[str, list[tuple[str, str]]] = {
    "VPN": [
        ("691", "VPN connection fails with error 691 after credential entry"),
        ("619", "VPN drops intermittently with error 619"),
        ("800", "Unable to establish VPN connection - error 800"),
        (None, "VPN client crashes on launch after Windows update"),
    ],
    "Authentication": [
        ("AUTH-401", "Repeated login failures against SSO provider"),
        ("MFA-102", "MFA push notifications not arriving on mobile app"),
        (None, "Password reset email never received"),
        ("AUTH-403", "Access denied to internal portal after role change"),
    ],
    "Network": [
        (None, "Intermittent packet loss on office Wi-Fi"),
        ("DNS-TIMEOUT", "Internal DNS resolution timing out"),
        (None, "VoIP calls dropping every few minutes"),
    ],
    "Endpoint Security": [
        ("EDR-509", "Endpoint agent reporting false positive quarantine"),
        (None, "Disk encryption status shows non-compliant"),
        ("EDR-233", "Antivirus definitions failing to update"),
    ],
    "Software": [
        (None, "Application crashes after latest patch release"),
        ("UPD-4021", "Update installation stuck at 40%"),
        (None, "License activation fails for licensed software"),
    ],
}

RESOLUTIONS = [
    "Reinstalled VPN client and re-authenticated; issue resolved.",
    "Rolled back Windows update KB via WSUS; VPN connectivity restored.",
    "Reset MFA enrollment for the user; push notifications resumed.",
    "Cleared DNS cache and restarted network adapter; resolved.",
    "Escalated to network team; faulty switch port replaced.",
    "Updated EDR agent to latest signature set; false positive cleared.",
    "Re-issued device certificate; authentication succeeded.",
    "Applied vendor hotfix; application no longer crashes.",
    "No action needed - transient provider outage, self-resolved.",
    "Reconfigured split-tunneling; VPN stability restored.",
]

SEVERITY_WEIGHTS = [
    (Severity.low, 0.35),
    (Severity.medium, 0.40),
    (Severity.high, 0.20),
    (Severity.critical, 0.05),
]


def _weighted_choice(weighted: list[tuple]) -> object:
    items, weights = zip(*weighted, strict=True)
    return random.choices(items, weights=weights, k=1)[0]


def seed_users(session, n: int = 60) -> list[User]:
    users = []
    for i in range(n):
        department = random.choice(DEPARTMENTS)
        user = User(
            employee_id=f"EMP{1000 + i}",
            full_name=fake.name(),
            email=fake.unique.company_email(),
            department=department,
            role=random.choice(ROLES),
            access_level=random.choice(["standard", "standard", "standard", "elevated"]),
            created_at=fake.date_time_between(start_date="-3y", end_date="-30d"),
        )
        session.add(user)
        users.append(user)
    session.flush()
    return users


def seed_devices(session, users: list[User]) -> list[Device]:
    devices = []
    for user in users:
        n_devices = random.choice([1, 1, 1, 2])
        for _ in range(n_devices):
            os_name, os_version = random.choice(OS_CHOICES)
            device = Device(
                asset_tag=f"AST-{fake.unique.random_number(digits=6)}",
                owner_id=user.id,
                device_type=random.choice(["laptop", "laptop", "desktop", "mobile"]),
                os_name=os_name,
                os_version=os_version,
                vpn_client_version=random.choice(VPN_CLIENT_VERSIONS)
                if os_name != "Linux"
                else None,
                last_seen_at=fake.date_time_between(start_date="-14d", end_date="now"),
                is_managed=random.random() > 0.1,
            )
            session.add(device)
            devices.append(device)
    session.flush()
    return devices


def seed_software_versions(session) -> None:
    products = [
        ("CorpVPN Client", ["4.10.2", "4.11.0", "4.11.3", "4.12.1", "5.0.0"]),
        ("Windows", ["22H2", "23H2", "24H2"]),
        ("EndpointGuard EDR", ["9.2.0", "9.3.1", "9.4.0"]),
        ("SSO Connector", ["2.1.0", "2.2.0"]),
    ]
    problematic = {("CorpVPN Client", "4.12.1"), ("Windows", "24H2")}
    base_date = datetime(2024, 1, 1)
    for product, versions in products:
        for i, version in enumerate(versions):
            session.add(
                SoftwareVersion(
                    product_name=product,
                    version=version,
                    release_date=base_date + timedelta(days=90 * i),
                    is_known_problematic=(product, version) in problematic,
                    notes=(
                        "Known to cause VPN authentication regressions on some "
                        "hardware configurations; see VPN Error Code Reference."
                        if (product, version) in problematic
                        else None
                    ),
                )
            )
    session.flush()


def seed_system_status(session) -> None:
    services = [
        "VPN Gateway (US-East)",
        "VPN Gateway (EU-West)",
        "SSO Identity Provider",
        "Internal DNS",
        "Ticketing System",
    ]
    for service in services:
        session.add(
            SystemStatus(
                service_name=service,
                status=random.choices(
                    ["operational", "degraded", "outage"], weights=[0.9, 0.08, 0.02]
                )[0],
                region="global",
                updated_at=datetime.utcnow(),
                details=None,
            )
        )
    session.flush()


def seed_incidents(
    session, users: list[User], devices: list[Device], n: int = 150
) -> list[Incident]:
    devices_by_owner = {}
    for d in devices:
        devices_by_owner.setdefault(d.owner_id, []).append(d)

    incidents = []
    for i in range(n):
        user = random.choice(users)
        user_devices = devices_by_owner.get(user.id, [])
        device = random.choice(user_devices) if user_devices else None
        category = random.choice(list(CATEGORY_TEMPLATES.keys()))
        error_code, title = random.choice(CATEGORY_TEMPLATES[category])
        severity = _weighted_choice(SEVERITY_WEIGHTS)
        created_at = fake.date_time_between(start_date="-180d", end_date="now")

        is_resolved = random.random() > 0.15
        status = IncidentStatus.resolved if is_resolved else random.choice(
            [IncidentStatus.open, IncidentStatus.in_progress]
        )
        resolved_at = (
            created_at + timedelta(hours=random.randint(1, 96)) if is_resolved else None
        )

        incident = Incident(
            incident_ref=f"INC-{10000 + i}",
            reported_by_id=user.id,
            device_id=device.id if device else None,
            category=category,
            error_code=error_code,
            title=title,
            description=(
                f"{title}. Reported by {user.full_name} ({user.department}). "
                f"Device: {device.os_name + ' ' + device.os_version if device else 'unknown'}."
            ),
            severity=severity,
            status=status,
            department=user.department,
            os_name=device.os_name if device else None,
            software_version=device.vpn_client_version if device else None,
            resolution=random.choice(RESOLUTIONS) if is_resolved else None,
            created_at=created_at,
            resolved_at=resolved_at,
        )
        session.add(incident)
        incidents.append(incident)

    session.flush()

    # A handful of related-incident links (e.g. a recurring VPN issue cluster)
    vpn_incidents = [inc for inc in incidents if inc.category == "VPN"]
    for inc in vpn_incidents[1::4]:
        candidate = random.choice(vpn_incidents)
        if candidate.id != inc.id:
            inc.related_incident_id = candidate.id

    # History entries for a sample of incidents
    for inc in random.sample(incidents, k=min(60, len(incidents))):
        session.add(
            IncidentHistory(
                incident_id=inc.id,
                changed_field="status",
                old_value="open",
                new_value=inc.status.value,
                changed_by=fake.user_name(),
                changed_at=inc.created_at + timedelta(hours=random.randint(1, 48)),
                note="Status updated during triage.",
            )
        )

    session.flush()
    return incidents


def seed_tickets(session, incidents: list[Incident]) -> None:
    sample = random.sample(incidents, k=min(40, len(incidents)))
    for i, inc in enumerate(sample):
        status = (
            TicketStatus.resolved
            if inc.status == IncidentStatus.resolved
            else TicketStatus.in_progress
        )
        session.add(
            Ticket(
                ticket_ref=f"TCK-{5000 + i}",
                incident_id=inc.id,
                title=f"Follow-up: {inc.title}",
                description=inc.description,
                status=status,
                priority=inc.severity.value,
                assigned_to=fake.user_name(),
                created_by="copilot-system",
                created_at=inc.created_at,
                updated_at=inc.resolved_at or inc.created_at,
            )
        )
    session.flush()


def seed_documents(session) -> None:
    """Register the synthetic SOP/guide markdown files under data/documents/
    as Document rows with metadata, so the SQL agent and RAG ingestion both
    have a consistent source of truth for what documents exist.
    """
    catalog = [
        ("vpn_troubleshooting_sop.md", DocumentType.sop, "IT Operations"),
        ("vpn_error_code_reference.md", DocumentType.reference, "IT Operations"),
        ("authentication_troubleshooting_guide.md", DocumentType.guide, "IT Operations"),
        ("mfa_troubleshooting_guide.md", DocumentType.guide, "IT Operations"),
        ("network_troubleshooting_manual.md", DocumentType.guide, "IT Operations"),
        ("windows_update_compatibility_guide.md", DocumentType.guide, "IT Operations"),
        ("endpoint_security_sop.md", DocumentType.sop, "Security"),
        ("password_reset_procedure.md", DocumentType.sop, "IT Operations"),
        ("incident_escalation_policy.md", DocumentType.policy, "IT Operations"),
        ("it_service_management_policy.md", DocumentType.policy, "IT Operations"),
        ("software_release_notes.md", DocumentType.release_notes, "Engineering"),
        ("network_maintenance_guide.md", DocumentType.guide, "IT Operations"),
        ("endpoint_configuration_guide.md", DocumentType.guide, "IT Operations"),
        ("security_incident_response_sop.md", DocumentType.sop, "Security"),
        ("remote_access_policy.md", DocumentType.policy, "Security"),
    ]
    for filename, doc_type, department in catalog:
        doc = Document(
            document_name=filename.replace("_", " ").replace(".md", "").title(),
            file_path=f"data/documents/{filename}",
            document_type=doc_type,
            department=department,
            version="1.0",
            access_level="standard",
            created_at=datetime.utcnow(),
        )
        session.add(doc)
        session.flush()
        session.add(
            DocumentMetadata(
                document_id=doc.id, section=None, key="owner_team", value=department
            )
        )
    session.flush()


def run(reset: bool = False) -> None:
    if reset:
        drop_db()
    init_db()

    with get_session() as session:
        existing_users = session.query(User).count()
        if existing_users and not reset:
            print(f"Database already seeded ({existing_users} users found). Use --reset to reseed.")
            return

        print("Seeding users...")
        users = seed_users(session)
        print("Seeding devices...")
        devices = seed_devices(session, users)
        print("Seeding software versions...")
        seed_software_versions(session)
        print("Seeding system status...")
        seed_system_status(session)
        print("Seeding incidents (+ history)...")
        incidents = seed_incidents(session, users, devices, n=150)
        print("Seeding tickets...")
        seed_tickets(session, incidents)
        print("Registering knowledge base documents...")
        seed_documents(session)

    print("Seed complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed synthetic enterprise data.")
    parser.add_argument("--reset", action="store_true", help="Drop and reseed all tables.")
    args = parser.parse_args()
    run(reset=args.reset)
