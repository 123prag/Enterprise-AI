"""System-state tools: check_system_status, check_software_version."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.database.models import SoftwareVersion, SystemStatus
from app.database.session import get_session
from app.tools.schemas import ToolOutput

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# check_system_status
# --------------------------------------------------------------------------


class CheckSystemStatusInput(BaseModel):
    service_name: str | None = None  # None = return all services


class ServiceStatus(BaseModel):
    service_name: str
    status: str
    region: str
    details: str | None


class CheckSystemStatusOutput(ToolOutput):
    services: list[ServiceStatus] = Field(default_factory=list)


def check_system_status(input: CheckSystemStatusInput) -> CheckSystemStatusOutput:
    try:
        with get_session() as session:
            stmt = select(SystemStatus)
            if input.service_name:
                stmt = stmt.where(SystemStatus.service_name == input.service_name)
            rows = session.execute(stmt).scalars().all()

        if input.service_name and not rows:
            return CheckSystemStatusOutput(
                success=False, error=f"Unknown service: {input.service_name!r}"
            )

        return CheckSystemStatusOutput(
            services=[
                ServiceStatus(
                    service_name=r.service_name,
                    status=r.status,
                    region=r.region,
                    details=r.details,
                )
                for r in rows
            ]
        )
    except SQLAlchemyError as e:
        logger.exception("check_system_status DB error")
        return CheckSystemStatusOutput(success=False, error=f"Database error: {e}")
    except Exception as e:  # noqa: BLE001
        logger.exception("check_system_status unexpected error")
        return CheckSystemStatusOutput(success=False, error=str(e))


# --------------------------------------------------------------------------
# check_software_version
# --------------------------------------------------------------------------


class CheckSoftwareVersionInput(BaseModel):
    product_name: str = Field(min_length=1)
    version: str = Field(min_length=1)


class CheckSoftwareVersionOutput(ToolOutput):
    product_name: str | None = None
    version: str | None = None
    is_known_problematic: bool = False
    notes: str | None = None
    latest_version: str | None = None


def check_software_version(input: CheckSoftwareVersionInput) -> CheckSoftwareVersionOutput:
    try:
        with get_session() as session:
            row = session.execute(
                select(SoftwareVersion).where(
                    SoftwareVersion.product_name == input.product_name,
                    SoftwareVersion.version == input.version,
                )
            ).scalar_one_or_none()

            latest = session.execute(
                select(SoftwareVersion)
                .where(SoftwareVersion.product_name == input.product_name)
                .order_by(SoftwareVersion.release_date.desc())
            ).scalars().first()

        if row is None:
            return CheckSoftwareVersionOutput(
                success=False,
                error=f"No record of {input.product_name} version {input.version}",
                latest_version=latest.version if latest else None,
            )

        return CheckSoftwareVersionOutput(
            product_name=row.product_name,
            version=row.version,
            is_known_problematic=row.is_known_problematic,
            notes=row.notes,
            latest_version=latest.version if latest else None,
        )
    except SQLAlchemyError as e:
        logger.exception("check_software_version DB error")
        return CheckSoftwareVersionOutput(success=False, error=f"Database error: {e}")
    except Exception as e:  # noqa: BLE001
        logger.exception("check_software_version unexpected error")
        return CheckSoftwareVersionOutput(success=False, error=str(e))
