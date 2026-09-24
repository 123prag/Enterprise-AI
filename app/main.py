"""FastAPI application entrypoint.

Wires in the full route set (chat, incidents, search, approvals, metrics,
evaluate) from app/api/routes.py, on top of the Phase 1 health check.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.api.routes import router as api_router
from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title="Enterprise AI Incident Resolution & Knowledge Copilot",
    version="0.1.0",
    description=(
        "Multi-agent AI system for enterprise IT incident diagnosis, "
        "combining RAG, SQL, tool use, and human-in-the-loop review."
    ),
)

app.include_router(api_router)


@app.get("/health", tags=["system"])
def health() -> dict:
    """Basic liveness/readiness probe."""
    return {
        "status": "ok",
        "app_env": settings.app_env,
        "llm_provider": settings.llm_provider,
        "vector_store_provider": settings.vector_store_provider,
    }
