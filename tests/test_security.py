"""Phase 7 tests: security utilities (rate limiter, auth abstraction).

Separate from test_guardrails.py because app.guardrails.security
re-exports from app.agents.sql_agent, which imports pydantic and
SQLAlchemy -- so this file requires the full dependency stack, unlike
the pure-stdlib input/output guardrail tests.
"""

from app.guardrails.security import RateLimiter, authenticate_bearer_token


def test_rate_limiter_allows_up_to_max_then_blocks():
    limiter = RateLimiter(max_requests=3, window_seconds=60)
    now = 1000.0
    assert limiter.allow("client-a", now=now) is True
    assert limiter.allow("client-a", now=now) is True
    assert limiter.allow("client-a", now=now) is True
    assert limiter.allow("client-a", now=now) is False  # 4th request in window


def test_rate_limiter_window_expires():
    limiter = RateLimiter(max_requests=1, window_seconds=10)
    assert limiter.allow("client-b", now=1000.0) is True
    assert limiter.allow("client-b", now=1005.0) is False  # still in window
    assert limiter.allow("client-b", now=1011.0) is True  # window has passed


def test_rate_limiter_keys_are_independent():
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    assert limiter.allow("client-x", now=0) is True
    assert limiter.allow("client-y", now=0) is True  # different key, own budget


def test_rate_limiter_remaining_reflects_usage():
    limiter = RateLimiter(max_requests=5, window_seconds=60)
    limiter.allow("client-c", now=0)
    limiter.allow("client-c", now=0)
    assert limiter.remaining("client-c", now=0) == 3


def test_auth_local_mode_no_op_when_no_token_configured():
    ctx = authenticate_bearer_token(provided_token=None, configured_token="")
    assert ctx.authenticated is True


def test_auth_rejects_wrong_token_when_configured():
    ctx = authenticate_bearer_token(provided_token="wrong", configured_token="secret123")
    assert ctx.authenticated is False


def test_auth_accepts_matching_token():
    ctx = authenticate_bearer_token(provided_token="secret123", configured_token="secret123")
    assert ctx.authenticated is True
