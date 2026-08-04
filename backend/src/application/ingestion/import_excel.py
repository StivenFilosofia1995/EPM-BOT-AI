"""Caso de uso: importar una parrilla de Excel.

Flujo: `fetch → extract → validate → stage(draft)`. Las etapas de `review` y
`publish` son del panel (P2B): **nada de lo que entra aquí llega a `published`
sin que una persona lo apruebe** (ADR 005).

Usa la conexión de migraciones porque es una tarea de administración que el
operador dispara desde el panel o la CLI, igual que el seed. Cuando P2B exponga
el endpoint, pasará por `TenantContext` y RLS como el resto.
"""

import asyncio
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from src.application.ingestion.schemas import ImportReport, RowStatus
from src.config.settings import get_settings
from src.domain.entities import IngestionRunStatus, PublicationStatus, SourceKind
from src.infrastructure.ingestion.excel.headers import normalize
from src.infrastructure.ingestion.excel.rooms import RoomCatalog
from src.infrastructure.ingestion.excel.source import ImportContext, XlsxProgramacionSource


@dataclass(frozen=True, slots=True)
class ImportResult:
    report: ImportReport
    ingestion_run_id: UUID
    activities_inserted: int
    activities_updated: int
    skipped_unchanged: bool = False

    def render(self) -> str:
        if self.skipped_unchanged:
            return (
                f"{self.report.file_name}: contenido idéntico a una corrida anterior, "
                "no se reprocesa."
            )
        return (
            f"{self.report.render()}\n"
            f"  guardadas: {self.activities_inserted} nuevas, "
            f"{self.activities_updated} actualizadas (todas en draft)\n"
            f"  ingestion_run: {self.ingestion_run_id}"
        )


def _content_hash(path: Path) -> str:
    """SHA-256 del archivo, para no reprocesar contenido idéntico (P2A §6)."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def _resolve_tenant(conn: AsyncConnection, slug: str) -> UUID:
    tenant_id = await conn.scalar(
        text("SELECT id FROM tenants WHERE slug = :slug"), {"slug": slug}
    )
    if tenant_id is None:
        raise ValueError(f"No existe el tenant '{slug}'. ¿Falta cargar el seed?")
    return cast("UUID", tenant_id)


async def _resolve_venue(conn: AsyncConnection, tenant_id: UUID, slug: str) -> UUID:
    venue_id = await conn.scalar(
        text("SELECT id FROM venues WHERE tenant_id = :t AND slug = :s"),
        {"t": tenant_id, "s": slug},
    )
    if venue_id is None:
        raise ValueError(f"No existe el espacio '{slug}' para este tenant")
    return cast("UUID", venue_id)


async def _load_room_catalog(
    conn: AsyncConnection, tenant_id: UUID, venue_id: UUID
) -> RoomCatalog:
    rows = await conn.execute(
        text("SELECT normalized_name, id FROM rooms WHERE tenant_id = :t AND venue_id = :v"),
        {"t": tenant_id, "v": venue_id},
    )
    return RoomCatalog(by_name={row[0]: row[1] for row in rows})


async def _ensure_source(conn: AsyncConnection, tenant_id: UUID, venue_id: UUID) -> UUID:
    """Fuente `excel_admin` del espacio. Es la primaria (ADR 009)."""
    name = f"Excel administrativo — {venue_id}"
    source_id = await conn.scalar(
        text("SELECT id FROM sources WHERE tenant_id = :t AND name = :n"),
        {"t": tenant_id, "n": name},
    )
    if source_id is not None:
        return cast("UUID", source_id)
    created = await conn.scalar(
        text(
            "INSERT INTO sources (tenant_id, kind, name, venue_id) "
            "VALUES (:t, :k, :n, :v) RETURNING id"
        ),
        {"t": tenant_id, "k": SourceKind.EXCEL_ADMIN.value, "n": name, "v": venue_id},
    )
    return cast("UUID", created)


async def import_excel(  # noqa: PLR0913
    *,
    path: Path,
    tenant_slug: str,
    venue_slug: str,
    year: int,
    month: int,
    force: bool = False,
) -> ImportResult:
    """Importa el archivo y deja las actividades en `draft`.

    Leer el archivo, calcular su hash y parsearlo con openpyxl son operaciones
    bloqueantes. Van en un hilo aparte para no congelar el bucle de eventos:
    hoy esto lo llama la CLI y daría igual, pero en P2B lo llamará un endpoint
    HTTP y ahí bloquearía a todos los demás usuarios mientras dura la carga.
    """
    if not await asyncio.to_thread(path.exists):
        raise FileNotFoundError(f"No existe el archivo: {path}")

    digest = await asyncio.to_thread(_content_hash, path)
    engine = create_async_engine(get_settings().migration_url)
    try:
        async with engine.begin() as conn:
            tenant_id = await _resolve_tenant(conn, tenant_slug)
            venue_id = await _resolve_venue(conn, tenant_id, venue_slug)
            source_id = await _ensure_source(conn, tenant_id, venue_id)

            if not force:
                previous = await conn.scalar(
                    text(
                        "SELECT id FROM ingestion_runs WHERE tenant_id = :t"
                        " AND source_id = :s AND content_hash = :h AND status = :ok"
                    ),
                    {
                        "t": tenant_id,
                        "s": source_id,
                        "h": digest,
                        "ok": IngestionRunStatus.SUCCEEDED.value,
                    },
                )
                if previous is not None:
                    empty = ImportReport(file_name=path.name, venue_slug=venue_slug)
                    return ImportResult(empty, previous, 0, 0, skipped_unchanged=True)

            catalog = await _load_room_catalog(conn, tenant_id, venue_id)
            report = await asyncio.to_thread(
                XlsxProgramacionSource().parse,
                path,
                ImportContext(
                    venue_slug=venue_slug,
                    year=year,
                    month=month,
                    rooms=catalog,
                    file_name=path.name,
                ),
            )

            started = datetime.now(UTC)
            run_id = cast(
                "UUID",
                await conn.scalar(
                    text(
                        "INSERT INTO ingestion_runs (tenant_id, source_id, status, started_at,"
                        " content_hash) VALUES (:t, :s, :st, :at, :h) RETURNING id"
                    ),
                    {
                        "t": tenant_id,
                        "s": source_id,
                        "st": IngestionRunStatus.RUNNING.value,
                        "at": started,
                        "h": digest,
                    },
                ),
            )

            inserted, updated = await _persist(
                conn,
                report=report,
                tenant_id=tenant_id,
                venue_id=venue_id,
                source_id=source_id,
            )

            await conn.execute(
                text(
                    "UPDATE ingestion_runs SET status = :st, finished_at = :fin,"
                    " rows_read = :read, rows_imported = :imp, rows_warning = :warn,"
                    " rows_error = :err, stats = :stats WHERE id = :id"
                ),
                {
                    "id": run_id,
                    "st": (
                        IngestionRunStatus.PARTIAL.value
                        if report.rows_error
                        else IngestionRunStatus.SUCCEEDED.value
                    ),
                    "fin": datetime.now(UTC),
                    "read": report.rows_read,
                    "imp": inserted + updated,
                    "warn": report.rows_warning,
                    "err": report.rows_error,
                    "stats": _stats_json(report, inserted, updated),
                },
            )
            await conn.execute(
                text("UPDATE sources SET last_run_at = :at WHERE id = :id"),
                {"at": datetime.now(UTC), "id": source_id},
            )
    finally:
        await engine.dispose()

    return ImportResult(report, run_id, inserted, updated)


def _stats_json(report: ImportReport, inserted: int, updated: int) -> str:
    import json  # noqa: PLC0415

    return json.dumps(
        {
            "activities_inserted": inserted,
            "activities_updated": updated,
            "unknown_columns": report.unknown_columns,
            "sheets_skipped": report.sheets_skipped,
        },
        ensure_ascii=False,
    )


async def _persist(
    conn: AsyncConnection,
    *,
    report: ImportReport,
    tenant_id: UUID,
    venue_id: UUID,
    source_id: UUID,
) -> tuple[int, int]:
    """Guarda las extracciones en `activities`, siempre como `draft`.

    Reimportar el mismo mes actualiza las filas existentes en vez de
    duplicarlas: la clave es (tenant, espacio, título normalizado, inicio),
    la misma del índice único de deduplicación.
    """
    inserted = updated = 0

    for row in report.rows:
        if row.status is RowStatus.ERROR:
            # Una fila con errores no puede publicarse ni guardarse: queda en
            # el reporte para que el operador la corrija (§9).
            continue

        for extraction in row.extractions:
            normalized_title = normalize(extraction.title)
            params: dict[str, Any] = {
                "t": tenant_id,
                "v": venue_id,
                "title": extraction.title,
                "ntitle": normalized_title,
                "starts": extraction.starts_at,
                "ends": extraction.ends_at,
                "desc": extraction.description,
                "room_id": extraction.room_id,
                "room_raw": extraction.room_raw,
                "recurrence": extraction.recurrence,
                "group_id": extraction.activity_group_id,
                "audience": extraction.audience.value if extraction.audience else None,
                "age_min": extraction.age_min,
                "age_max": extraction.age_max,
                "audience_raw": extraction.audience_raw,
                "req_reg": extraction.requires_registration,
                "reg_url": extraction.registration_url,
                "status": PublicationStatus.DRAFT.value,
                "source_id": source_id,
                "source_row": extraction.source_row,
                "evidence": extraction.evidence_snippet,
                "extracted_at": datetime.now(UTC),
                "confidence": extraction.confidence,
                "warnings": [w.value for w in extraction.warnings],
                "extra": _stats_dump(extraction.extra),
            }

            existing = await conn.scalar(
                text(
                    "SELECT id FROM activities WHERE tenant_id = :t AND venue_id = :v"
                    " AND normalized_title = :ntitle AND starts_at = :starts"
                    " AND deleted_at IS NULL"
                ),
                params,
            )

            if existing is None:
                await conn.execute(
                    text(
                        "INSERT INTO activities (tenant_id, venue_id, title, normalized_title,"
                        " description, starts_at, ends_at, room_id, room_raw, recurrence,"
                        " activity_group_id, audience, age_min, age_max, audience_raw,"
                        " requires_registration, registration_url, status, source_id,"
                        " source_row, evidence_snippet, extracted_at, confidence, warnings, extra)"
                        " VALUES (:t, :v, :title, :ntitle, :desc, :starts, :ends, :room_id,"
                        " :room_raw, :recurrence, :group_id, :audience, :age_min, :age_max,"
                        " :audience_raw, :req_reg, :reg_url, :status, :source_id, :source_row,"
                        " :evidence, :extracted_at, :confidence, :warnings, :extra)"
                    ),
                    params,
                )
                inserted += 1
            else:
                # Solo se re-escriben filas que siguen en draft: si alguien ya
                # revisó y publicó una actividad, una reimportación no puede
                # devolverla a draft por la espalda.
                result = await conn.execute(
                    text(
                        "UPDATE activities SET title = :title, description = :desc,"
                        " ends_at = :ends, room_id = :room_id, room_raw = :room_raw,"
                        " recurrence = :recurrence, activity_group_id = :group_id,"
                        " audience = :audience, age_min = :age_min, age_max = :age_max,"
                        " audience_raw = :audience_raw, requires_registration = :req_reg,"
                        " registration_url = :reg_url, source_id = :source_id,"
                        " source_row = :source_row, evidence_snippet = :evidence,"
                        " extracted_at = :extracted_at, confidence = :confidence,"
                        " warnings = :warnings, extra = :extra"
                        " WHERE id = :id AND status = :status"
                    ),
                    {**params, "id": existing},
                )
                updated += result.rowcount or 0

    return inserted, updated


def _stats_dump(value: dict[str, Any]) -> str:
    import json  # noqa: PLC0415

    return json.dumps(value, ensure_ascii=False, default=str)
