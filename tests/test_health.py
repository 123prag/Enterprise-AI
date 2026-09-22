"""Phase 1 smoke test: the app boots and /health responds correctly."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app_env"] == "local"


def test_settings_default_to_local_offline_mode():
    from app.config import get_settings

    settings = get_settings()
    assert settings.llm_provider == "dummy"
    assert settings.vector_store_provider == "faiss"
    assert settings.database_url.startswith("sqlite:///")
