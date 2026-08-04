"""Rutas de programación: carga de Excel y consulta de actividades.

La carga tiene dos pasos a propósito:

1. `POST /import/preview` — parsea y devuelve qué se interpretó, **sin escribir
   nada**. El operador puede subir un archivo equivocado y verlo sin
   consecuencias.
2. `POST /import` — persiste, siempre como `draft`.

Publicar no se hace desde aquí. Es un acto humano separado (ADR 005).
"""

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import text

from src.application.ingestion.import_excel import import_excel_bytes, preview_excel
from src.application.ingestion.schemas import ImportReport
from src.config.settings import get_settings
from src.infrastructure.database.session import tenant_session
from src.presentation.dependencies import AdminGuard, CurrentTenant

router = APIRouter(tags=["programación"])

#: Límite de subida. Las parrillas reales pesan decenas de KB; 10 MB es margen
#: de sobra y evita que una subida enorme agote la memoria del proceso.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

ALLOWED_SUFFIXES = (".xlsx", ".xlsm")


class VenueOut(BaseModel):
    slug: str
    name: str
    kind: str


class ActivityOut(BaseModel):
    """Actividad tal cual está guardada.

    Las fechas van en **UTC**; el cliente las formatea a `America/Bogota`. No
    se envían pre-formateadas para que el frontend no tenga que deshacer un
    formato y no haya dos verdades sobre la hora.
    """

    id: str
    title: str
    description: str | None
    venue_slug: str
    room_name: str | None
    room_raw: str | None
    starts_at: datetime
    ends_at: datetime | None
    audience: str | None
    audience_raw: str | None
    age_min: int | None
    age_max: int | None
    requires_registration: bool | None
    registration_url: str | None
    status: str
    confidence: float
    warnings: list[str]
    source_row: str | None
    evidence_snippet: str | None


class ActivityPage(BaseModel):
    items: list[ActivityOut]
    total: int
    limit: int
    offset: int


class ImportSummary(BaseModel):
    """Resumen que ve el operador. Todos los números salen del informe real
    de la importación; ninguno se estima."""

    file_name: str
    venue_slug: str
    rows_read: int
    rows_ok: int
    rows_warning: int
    rows_error: int
    activities: int
    unknown_columns: list[str]
    sheets_skipped: list[str]


class PreviewRow(BaseModel):
    sheet: str
    row_number: int
    status: Literal["ok", "warning", "error"]
    title: str | None
    dates_raw: str | None
    time_raw: str | None
    room_raw: str | None
    audience_raw: str | None
    activities: int
    warnings: list[str]
    errors: list[str]
    starts_at: list[datetime]


class PreviewOut(BaseModel):
    summary: ImportSummary
    rows: list[PreviewRow]


class ImportOut(BaseModel):
    summary: ImportSummary
    ingestion_run_id: str | None
    activities_inserted: int
    activities_updated: int
    skipped_unchanged: bool
    message: str


def _summary(report: ImportReport) -> ImportSummary:
    return ImportSummary(
        file_name=report.file_name,
        venue_slug=report.venue_slug,
        rows_read=report.rows_read,
        rows_ok=report.rows_ok,
        rows_warning=report.rows_warning,
        rows_error=report.rows_error,
        activities=len(report.extractions),
        unknown_columns=report.unknown_columns,
        sheets_skipped=report.sheets_skipped,
    )


def _preview_rows(report: ImportReport) -> list[PreviewRow]:
    def cell(row: Any, key: str) -> str | None:
        value = row.raw.get(key)
        return str(value).strip() if value is not None and str(value).strip() else None

    return [
        PreviewRow(
            sheet=row.sheet,
            row_number=row.row_number,
            status=row.status.value,
            title=cell(row, "title"),
            dates_raw=cell(row, "dates_raw"),
            time_raw=cell(row, "time_raw"),
            room_raw=cell(row, "room_raw"),
            audience_raw=cell(row, "audience_raw"),
            activities=len(row.extractions),
            warnings=[w.value for w in row.warnings],
            errors=row.errors,
            starts_at=[e.starts_at for e in row.extractions],
        )
        for row in report.rows
    ]


async def _read_upload(file: UploadFile) -> bytes:
    """Valida y lee la subida.

    Se comprueba la extensión y el tamaño real leído, no el `content-type` ni
    la cabecera `content-length`: ambos los controla el cliente y se pueden
    falsear.
    """
    name = (file.filename or "").lower()
    if not name.endswith(ALLOWED_SUFFIXES):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Solo se admiten archivos {' o '.join(ALLOWED_SUFFIXES)}",
        )

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"El archivo supera el límite de {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
        )
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo está vacío"
        )
    return content


def _parse_month(raw: str) -> tuple[int, int]:
    try:
        year, month = raw.split("-")
        parsed = (int(year), int(month))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"El mes debe tener el formato AAAA-MM, no {raw!r}",
        ) from None
    if not 1 <= parsed[1] <= 12:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Mes fuera de rango: {parsed[1]}",
        )
    return parsed


@router.get("/venues", response_model=list[VenueOut])
async def list_venues(_: AdminGuard, tenant: CurrentTenant) -> list[VenueOut]:
    """Espacios del tenant, para el selector de la pantalla de carga."""
    async with tenant_session(tenant.tenant_id) as session:
        rows = await session.execute(
            text("SELECT slug, name, kind FROM venues ORDER BY kind, name")
        )
        return [VenueOut(slug=r[0], name=r[1], kind=r[2]) for r in rows]


@router.get("/activities", response_model=ActivityPage)
async def list_activities(  # noqa: PLR0913
    _: AdminGuard,
    tenant: CurrentTenant,
    venue: Annotated[str | None, Query(description="slug del espacio")] = None,
    month: Annotated[str | None, Query(description="AAAA-MM")] = None,
    activity_status: Annotated[str | None, Query(alias="status")] = None,
    only_warnings: Annotated[bool, Query()] = False,
    search: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ActivityPage:
    """Listado paginado, filtrado en servidor.

    El filtro de mes se resuelve contra la hora de Bogotá: preguntar por
    «julio» debe devolver lo que el usuario ve como julio, no lo que cae en
    julio en UTC.
    """
    conditions = ["a.deleted_at IS NULL"]
    params: dict[str, Any] = {"limit": limit, "offset": offset}

    if venue:
        conditions.append("v.slug = :venue")
        params["venue"] = venue
    if activity_status:
        conditions.append("a.status = :status")
        params["status"] = activity_status
    if only_warnings:
        conditions.append("cardinality(a.warnings) > 0")
    if search:
        conditions.append("a.title ILIKE :search")
        params["search"] = f"%{search}%"
    if month:
        year, month_number = _parse_month(month)
        conditions.append(
            "date_trunc('month', a.starts_at AT TIME ZONE 'America/Bogota') = :month_start"
        )
        params["month_start"] = datetime(year, month_number, 1)  # noqa: DTZ001

    where = " AND ".join(conditions)
    async with tenant_session(tenant.tenant_id) as session:
        total = await session.scalar(
            text(  # noqa: S608
                "SELECT count(*) FROM activities a"
                " JOIN venues v ON v.id = a.venue_id"
                f" WHERE {where}"
            ),
            params,
        )
        rows = await session.execute(
            text(  # noqa: S608
                "SELECT a.id, a.title, a.description, v.slug, r.name, a.room_raw,"
                " a.starts_at, a.ends_at, a.audience, a.audience_raw, a.age_min, a.age_max,"
                " a.requires_registration, a.registration_url, a.status, a.confidence,"
                " a.warnings, a.source_row, a.evidence_snippet"
                " FROM activities a"
                " JOIN venues v ON v.id = a.venue_id"
                " LEFT JOIN rooms r ON r.id = a.room_id"
                f" WHERE {where}"
                " ORDER BY a.starts_at, a.title"
                " LIMIT :limit OFFSET :offset"
            ),
            params,
        )
        items = [
            ActivityOut(
                id=str(r[0]),
                title=r[1],
                description=r[2],
                venue_slug=r[3],
                room_name=r[4],
                room_raw=r[5],
                starts_at=r[6],
                ends_at=r[7],
                audience=r[8],
                audience_raw=r[9],
                age_min=r[10],
                age_max=r[11],
                requires_registration=r[12],
                registration_url=r[13],
                status=r[14],
                confidence=float(r[15]),
                warnings=list(r[16] or []),
                source_row=r[17],
                evidence_snippet=r[18],
            )
            for r in rows
        ]

    return ActivityPage(items=items, total=total or 0, limit=limit, offset=offset)


@router.post("/programacion/import/preview", response_model=PreviewOut)
async def preview_import(
    _: AdminGuard,
    tenant: CurrentTenant,
    file: Annotated[UploadFile, File()],
    venue: Annotated[str, Form()],
    month: Annotated[str, Form(description="AAAA-MM")],
) -> PreviewOut:
    """Parsea el archivo y devuelve qué se interpretó, **sin guardar nada**."""
    content = await _read_upload(file)
    year, month_number = _parse_month(month)

    try:
        report = await preview_excel(
            content=content,
            tenant_slug=tenant.tenant_slug or get_settings().default_tenant_slug,
            venue_slug=venue,
            year=year,
            month=month_number,
            file_name=file.filename or "programacion.xlsx",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except Exception as exc:  # noqa: BLE001
        # Un archivo corrupto o que no es un Excel real llega hasta openpyxl.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"No se pudo leer el archivo como Excel: {exc}",
        ) from exc

    return PreviewOut(summary=_summary(report), rows=_preview_rows(report))


@router.post("/programacion/import", response_model=ImportOut)
async def run_import(  # noqa: PLR0913
    _: AdminGuard,
    tenant: CurrentTenant,
    file: Annotated[UploadFile, File()],
    venue: Annotated[str, Form()],
    month: Annotated[str, Form(description="AAAA-MM")],
    force: Annotated[bool, Form()] = False,
) -> ImportOut:
    """Importa el archivo. Todo entra como `draft`; nada se publica aquí."""
    content = await _read_upload(file)
    year, month_number = _parse_month(month)

    try:
        result = await import_excel_bytes(
            content=content,
            tenant_slug=tenant.tenant_slug or get_settings().default_tenant_slug,
            venue_slug=venue,
            year=year,
            month=month_number,
            force=force,
            file_name=file.filename or "programacion.xlsx",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"No se pudo importar el archivo: {exc}",
        ) from exc

    if result.skipped_unchanged:
        message = (
            "Este archivo ya se importó antes y su contenido no ha cambiado, "
            "así que no se reprocesó. Marca «forzar» si quieres reimportarlo igualmente."
        )
    else:
        message = (
            f"{result.activities_inserted} actividades nuevas y "
            f"{result.activities_updated} actualizadas, todas en borrador."
        )

    return ImportOut(
        summary=_summary(result.report),
        ingestion_run_id=str(result.ingestion_run_id) if result.ingestion_run_id else None,
        activities_inserted=result.activities_inserted,
        activities_updated=result.activities_updated,
        skipped_unchanged=result.skipped_unchanged,
        message=message,
    )


__all__ = ["MAX_UPLOAD_BYTES", "router"]
