"""Security utilities shared across the API and agents.

- SQL injection prevention: re-exports the SQL agent's validator so
  callers have a single ``app.guardrails`` surface to import from,
  without duplicating the safety logic (the one implementation lives in
  ``app/agents/sql_agent.py`` since that's where it's actually applied).
- Rate limiting: an in-memory sliding-window limiter. Deliberately simple
  (no Redis dependency) -- adequate for a single-process deployment and
  swappable for a distributed limiter later without changing the
  interface.
- Authentication: a minimal bearer-token abstraction. Real identity
  provider integration is out of scope for this project; this exists so
  the FastAPI layer (Phase 8) has a consistent seam to call rather than
  hand-checking headers inline.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass

# SQL injection prevention is re-exported lazily (PEP 562 module __getattr__)
# rather than imported at module load time: app.agents.sql_agent pulls in
# pydantic + SQLAlchemy, but RateLimiter/AuthContext below need neither,
# and callers that only need rate limiting or auth shouldn't be forced to
# have the DB stack installed just to import this module.


def __getattr__(name: str):
    if name in ("validate_readonly_sql", "SQLSafetyError"):
        from app.agents import sql_agent

        return getattr(sql_agent, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# --------------------------------------------------------------------------
# Rate limiting
# --------------------------------------------------------------------------


class RateLimiter:
    """Sliding-window rate limiter, keyed by an arbitrary client identifier
    (API token, IP, user id). Not thread-safe across processes -- fine for
    a single-process deployment; swap for a Redis-backed limiter behind
    the same ``allow(key)`` interface for multi-process/production use.
    """

    def __init__(self, max_requests: int, window_seconds: float = 60.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)

    def allow(self, key: str, now: float | None = None) -> bool:
        now = now if now is not None else time.monotonic()
        window_start = now - self.window_seconds
        hits = self._hits[key]

        # Drop expired hits
        while hits and hits[0] < window_start:
            hits.pop(0)

        if len(hits) >= self.max_requests:
            return False

        hits.append(now)
        return True

    def remaining(self, key: str, now: float | None = None) -> int:
        now = now if now is not None else time.monotonic()
        window_start = now - self.window_seconds
        hits = [h for h in self._hits[key] if h >= window_start]
        return max(0, self.max_requests - len(hits))


# --------------------------------------------------------------------------
# Authentication abstraction
# --------------------------------------------------------------------------


@dataclass
class AuthContext:
    authenticated: bool
    user_id: str | None = None
    access_level: str = "standard"


def authenticate_bearer_token(provided_token: str | None, configured_token: str) -> AuthContext:
    """Minimal bearer-token check. If ``configured_token`` is empty (the
    local-mode default), authentication is a no-op that always succeeds --
    appropriate for local development, never for a real deployment. In
    production, ``API_AUTH_TOKEN`` must be set for this to mean anything.
    """
    if not configured_token:
        return AuthContext(authenticated=True, user_id="local-dev", access_level="standard")

    if provided_token and provided_token == configured_token:
        return AuthContext(authenticated=True, user_id="api-client", access_level="standard")

    return AuthContext(authenticated=False)
