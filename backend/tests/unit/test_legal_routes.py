"""Páginas públicas de política de privacidad y eliminación de datos,
exigidas por Meta para dar de alta la app de WhatsApp Business."""

from fastapi.testclient import TestClient

from src.presentation.main import app


def test_privacy_policy_is_publicly_reachable() -> None:
    with TestClient(app) as client:
        response = client.get("/privacidad")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Fundación Grupo" in response.text


def test_data_deletion_instructions_are_publicly_reachable() -> None:
    with TestClient(app) as client:
        response = client.get("/eliminar-datos")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "ELIMINAR MIS DATOS" in response.text
