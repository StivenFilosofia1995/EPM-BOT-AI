"""Prueba de humo del endpoint /health (criterio de aceptación de P0)."""

from fastapi.testclient import TestClient

from src.presentation.main import app


def test_health_returns_200_ok() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_error_responses_use_the_standard_envelope() -> None:
    with TestClient(app) as client:
        response = client.get("/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert "error" in body
    assert {"code", "message", "details", "trace_id"} <= body["error"].keys()
