"""Database engine/session management.

Works against SQLite (local dev, default) or PostgreSQL (production) purely
based on ``settings.database_url`` — no code elsewhere should construct an
engine directly.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.database.models import Base

settings = get_settings()

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=_connect_args, future=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    """Create all tables if they don't already exist.

    Safe to call repeatedly (idempotent, does not drop/alter existing
    tables). Schema migrations for production should use Alembic instead
    of relying on this for anything beyond first-run bootstrap and tests.
    """
    Base.metadata.create_all(bind=engine)


def drop_db() -> None:
    """Drop all tables. Used by tests/seed scripts only — never call in prod."""
    Base.metadata.drop_all(bind=engine)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Context-managed session for scripts and non-FastAPI code paths."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a session, closes it after the request."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
