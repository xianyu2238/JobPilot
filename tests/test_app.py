"""Verify startup, health, and interactive API documentation without a network."""

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_health_and_documentation() -> None:
    application = create_app(Settings(_env_file=None, environment="test"))
    with TestClient(application) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        docs = client.get("/docs")
        assert docs.status_code == 200
        assert "text/html" in docs.headers["content-type"]
        schema = client.get("/openapi.json")
        assert schema.status_code == 200
        assert "/health" in schema.json()["paths"]
