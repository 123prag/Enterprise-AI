"""FastAPI application entrypoint.

Phase 1 only wires up the app skeleton and a health check so the repo is
runnable end-to-end from commit one. Subsequent phases add the real
routes (/chat, /incidents, /search, /approve-action, ...) in app/api/routes.py.
"""

from __future__ import annotations

from fastapi import FastAPI

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


@app.get("/health", tags=["system"])
def health() -> dict:
    """Basic liveness/readiness probe."""
    return {
        "status": "ok",
        "app_env": settings.app_env,
        "llm_provider": settings.llm_provider,
        "vector_store_provider": settings.vector_store_provider,
    }
