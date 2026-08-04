"""La vista previa no escribe en la base de datos.

Es la promesa que sostiene toda la pantalla de carga: el operador puede subir
un archivo equivocado y verlo sin consecuencias. Si esto se rompiera, un
archivo mal elegido ensuciaría la programación antes de que nadie lo revise.

Se comprueba contra la base real, no con dobles: el punto es justamente que
nada llegó a persistirse.

Requiere base de datos y el archivo de programación real; se salta si falta
cualquiera de los dos.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from src.application.ingestion.import_excel import preview_excel
from src.config.settings import get_settings

pytestmark = pytest.mark.integration

#: Archivo real de la Fundación, en la raíz del repositorio.
REAL_FILE = (
    Path(__file__).resolve().parents[3] / "Programacion_Formativa Biblioteca_Julio_2026.xlsx"
)

TENANT_SLUG = "fundacion-epm"
VENUE_SLUG = "biblioteca-epm"


def _requires_db() -> None:
    settings = get_settings()
    if "localhost" in settings.database_url or not settings.database_migration_url:
        pytest.skip("Sin base de datos real configurada (DATABASE_MIGRATION_URL)")


@pytest_asyncio.fixture
async def admin_conn() -> AsyncIterator[AsyncConnection]:
    _requires_db()
    engine = create_async_engine(get_settings().migration_url)
    async with engine.connect() as conn:
        yield conn
    await engine.dispose()


async def _counts(conn: AsyncConnection) -> tuple[int, int, int]:
    """Actividades, corridas de ingesta y fuentes registradas."""
    activities = await conn.scalar(text("SELECT count(*) FROM activities"))
    runs = await conn.scalar(text("SELECT count(*) FROM ingestion_runs"))
    sources = await conn.scalar(text("SELECT count(*) FROM sources"))
    return (activities or 0, runs or 0, sources or 0)


async def test_preview_leaves_the_database_untouched(admin_conn: AsyncConnection) -> None:
    if not REAL_FILE.exists():
        pytest.skip(f"No está el archivo de programación real: {REAL_FILE.name}")

    before = await _counts(admin_conn)

    report = await preview_excel(
        content=REAL_FILE.read_bytes(),
        tenant_slug=TENANT_SLUG,
        venue_slug=VENUE_SLUG,
        year=2026,
        month=7,
        file_name=REAL_FILE.name,
    )

    # La vista previa sí devuelve resultados: si no leyera nada, el test de
    # «no escribió» pasaría por el motivo equivocado.
    assert report.rows_read > 0
    assert len(report.extractions) > 0

    after = await _counts(admin_conn)
    assert after == before, (
        "La vista previa modificó la base de datos: "
        f"actividades/corridas/fuentes pasaron de {before} a {after}"
    )
