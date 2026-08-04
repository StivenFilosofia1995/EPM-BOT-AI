"""Tests de las rutas de programación.

Aquí se prueba solo la capa HTTP: guarda de token, validación de la subida y
de los parámetros. Nada toca la base de datos — las dependencias que resuelven
el tenant se sustituyen, y las validaciones que se comprueban ocurren *antes*
de cualquier consulta.

Que la vista previa no escriba nada se verifica de verdad en el test de
integración; aquí se comprueba que un archivo rechazado ni siquiera llega al
importador.
"""

from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.application.ingestion.schemas import ImportReport
from src.application.tenancy import TenantContext
from src.config.settings import Settings, get_settings
from src.domain.value_objects import TenantId
from src.presentation.dependencies import get_tenant_context
from src.presentation.main import app
from src.presentation.routers import programacion

TOKEN = "token-de-prueba-1234567890"
AUTH = {"X-Admin-Token": TOKEN}
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

PREVIEW_URL = "/api/v1/programacion/import/preview"
IMPORT_URL = "/api/v1/programacion/import"


def _settings_with_token(token: str | None) -> Settings:
    """Copia de la configuración real cambiando solo el token."""
    base = get_settings()
    return base.model_copy(update={"admin_api_token": token})


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Cliente con token configurado y el tenant ya resuelto.

    Se sustituye `get_tenant_context` porque su implementación real consulta
    la base de datos: estos tests no deben depender de que haya una.
    """
    app.dependency_overrides[get_settings] = lambda: _settings_with_token(TOKEN)
    app.dependency_overrides[get_tenant_context] = lambda: TenantContext(
        tenant_id=TenantId(uuid4()), tenant_slug="tenant-de-prueba"
    )
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def no_importing(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Hace explotar el importador.

    Si una petición que debía rechazarse llega hasta aquí, el test falla con
    un mensaje claro en vez de intentar conectarse a la base de datos.
    """
    calls: list[str] = []

    def explode(*_args: Any, **_kwargs: Any) -> Any:
        calls.append("llamado")
        raise AssertionError("El importador no debería haberse ejecutado")

    monkeypatch.setattr(programacion, "preview_excel", explode)
    monkeypatch.setattr(programacion, "import_excel_bytes", explode)
    return calls


def _upload(name: str = "parrilla.xlsx", content: bytes = b"PK\x03\x04datos") -> dict[str, Any]:
    return {"file": (name, content, XLSX)}


def _form(**overrides: str) -> dict[str, str]:
    return {"venue": "biblioteca-epm", "month": "2026-07", **overrides}


# --- Guarda de administración -------------------------------------------------


@pytest.mark.parametrize("url", [PREVIEW_URL, IMPORT_URL])
def test_upload_without_token_is_rejected(
    client: TestClient, no_importing: list[str], url: str
) -> None:
    response = client.post(url, files=_upload(), data=_form())

    assert response.status_code == 401
    assert no_importing == []


@pytest.mark.parametrize("url", [PREVIEW_URL, IMPORT_URL])
def test_upload_with_wrong_token_is_rejected(
    client: TestClient, no_importing: list[str], url: str
) -> None:
    response = client.post(
        url, files=_upload(), data=_form(), headers={"X-Admin-Token": "token-equivocado"}
    )

    assert response.status_code == 401
    assert no_importing == []


def test_read_endpoints_also_require_the_token(client: TestClient) -> None:
    assert client.get("/api/v1/venues").status_code == 401
    assert client.get("/api/v1/activities").status_code == 401


def test_routes_are_disabled_when_no_token_is_configured(no_importing: list[str]) -> None:
    """Sin `ADMIN_API_TOKEN` el panel se apaga, no se abre."""
    app.dependency_overrides[get_settings] = lambda: _settings_with_token(None)
    try:
        with TestClient(app) as test_client:
            response = test_client.get("/api/v1/venues", headers=AUTH)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503


# --- Validación de la subida --------------------------------------------------


@pytest.mark.parametrize("filename", ["parrilla.csv", "parrilla.pdf", "parrilla.xls", "parrilla"])
def test_non_excel_files_are_rejected(
    client: TestClient, no_importing: list[str], filename: str
) -> None:
    response = client.post(
        PREVIEW_URL, files=_upload(name=filename), data=_form(), headers=AUTH
    )

    assert response.status_code == 415
    assert no_importing == []


@pytest.mark.parametrize("filename", ["PARRILLA.XLSX", "macro.xlsm"])
def test_accepted_extensions_are_case_insensitive(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, filename: str
) -> None:
    """No debe rechazarse por la extensión: llega al importador."""
    seen: list[str] = []

    async def fake_preview(*, file_name: str, venue_slug: str, **_kwargs: Any) -> ImportReport:
        seen.append(file_name)
        return ImportReport(file_name=file_name, venue_slug=venue_slug)

    monkeypatch.setattr(programacion, "preview_excel", fake_preview)

    response = client.post(
        PREVIEW_URL, files=_upload(name=filename), data=_form(), headers=AUTH
    )

    assert response.status_code == 200
    assert seen == [filename]


def test_preview_of_a_file_with_no_rows_reports_zero_and_not_an_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un Excel sin filas es un resultado válido, no un fallo.

    Importa porque la interfaz distingue «no hay filas» de «falló la lectura»,
    y lo que muestra sale de estos números: nunca de un valor de ejemplo.
    """

    async def empty_report(*, file_name: str, venue_slug: str, **_kwargs: Any) -> ImportReport:
        return ImportReport(
            file_name=file_name, venue_slug=venue_slug, sheets_skipped=["Portada"]
        )

    monkeypatch.setattr(programacion, "preview_excel", empty_report)

    response = client.post(PREVIEW_URL, files=_upload(), data=_form(), headers=AUTH)

    assert response.status_code == 200
    body = response.json()
    assert body["rows"] == []
    assert body["summary"]["rows_read"] == 0
    assert body["summary"]["activities"] == 0
    assert body["summary"]["sheets_skipped"] == ["Portada"]


def test_a_corrupt_file_gives_a_422_with_the_reason(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un archivo ilegible no debe salir como 500."""

    async def boom(**_kwargs: Any) -> ImportReport:
        raise ValueError("El archivo no tiene la fila de encabezados esperada")

    monkeypatch.setattr(programacion, "preview_excel", boom)

    response = client.post(PREVIEW_URL, files=_upload(), data=_form(), headers=AUTH)

    assert response.status_code == 422
    # El motivo llega al operador: la interfaz lo muestra tal cual.
    assert "encabezados" in response.json()["error"]["message"]


def test_files_over_the_size_limit_are_rejected(
    client: TestClient, no_importing: list[str]
) -> None:
    oversized = b"x" * (programacion.MAX_UPLOAD_BYTES + 1)

    response = client.post(
        PREVIEW_URL, files=_upload(content=oversized), data=_form(), headers=AUTH
    )

    assert response.status_code == 413
    assert no_importing == []


def test_empty_files_are_rejected(client: TestClient, no_importing: list[str]) -> None:
    response = client.post(PREVIEW_URL, files=_upload(content=b""), data=_form(), headers=AUTH)

    assert response.status_code == 400
    assert no_importing == []


# --- Validación del mes -------------------------------------------------------


@pytest.mark.parametrize("month", ["julio", "2026/07", "2026-13", "2026-00", "07-2026", ""])
def test_malformed_month_is_rejected(
    client: TestClient, no_importing: list[str], month: str
) -> None:
    response = client.post(
        PREVIEW_URL, files=_upload(), data=_form(month=month), headers=AUTH
    )

    assert response.status_code == 422
    assert no_importing == []


@pytest.mark.parametrize("month", ["julio", "2026-13"])
def test_activities_filter_rejects_a_malformed_month(client: TestClient, month: str) -> None:
    response = client.get(f"/api/v1/activities?month={month}", headers=AUTH)

    assert response.status_code == 422


@pytest.mark.parametrize("query", ["limit=0", "limit=500", "offset=-1"])
def test_pagination_bounds_are_enforced(client: TestClient, query: str) -> None:
    response = client.get(f"/api/v1/activities?{query}", headers=AUTH)

    assert response.status_code == 422
