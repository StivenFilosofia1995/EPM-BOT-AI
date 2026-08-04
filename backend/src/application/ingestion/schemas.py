"""Esquemas del pipeline de ingesta.

`ActivityExtraction` es el contrato de salida de TODA fuente: lo produce igual
el importador de Excel (determinista) que el estructurador con LLM para PDF y
HTML. Que ambos caminos converjan aquí es lo que permite que el resto del
pipeline —deduplicación, revisión, publicación— no sepa de dónde vino el dato.

Ver `docs/CONTRATO_EXCEL_PROGRAMACION.md` §9.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.domain.value_objects import Audience


class RowStatus(StrEnum):
    """Resultado de procesar una fila.

    `ERROR` no aborta el archivo: se reporta la fila y se sigue con las
    demás (contrato §2).
    """

    OK = "ok"
    WARNING = "warning"
    ERROR = "error"


class IngestionWarning(StrEnum):
    """Advertencias conocidas. Son un enum y no texto libre para que el panel
    pueda filtrar y contar por tipo."""

    OUT_OF_MONTH = "out_of_month"
    """Fecha fuera del mes de la carga. Se importa igual: 'Del 23 de junio al
    9 de julio' es un caso legítimo (contrato §3.3)."""

    ROOM_FUZZY_MATCH = "room_fuzzy_match"
    """La sala se resolvió por coincidencia difusa; conviene revisarla."""

    ROOM_UNKNOWN = "room_unknown"
    """La sala no está en el catálogo. NO se crea automáticamente (§5)."""

    REGISTRATION_UNRESOLVED = "registration_unresolved"
    """Inscripción vacía y sin enlace: no se asume nada (§7)."""

    REGISTRATION_INCONSISTENT = "registration_inconsistent"
    """Dice 'No requiere inscripción' pero trae enlace (§7)."""

    REGISTRATION_NOT_A_URL = "registro_no_es_url"
    """La columna de enlace trae texto que no es una URL.

    Caso real del archivo de julio 2026: 'No disponible por cúpos
    completados'. El contrato §7 no lo cubría; se guarda el texto en `extra`
    y se deja la inscripción sin resolver, nunca prosa en un campo de URL."""

    AUDIENCE_FROM_SHEET_NAME = "audience_from_sheet_name"
    """El público se dedujo del nombre de la hoja porque la celda venía
    vacía. Confianza reducida (§6)."""

    MONTH_FROM_PARAMETER = "month_from_parameter"
    """No se pudo leer el mes del título de la fila 1 y se usó el del
    parámetro de carga. Confianza reducida (§3)."""

    NO_END_TIME = "no_end_time"
    """Sin hora de fin. Prohibido asumir duración (§4)."""

    UNKNOWN_COLUMNS = "unknown_columns"
    """El archivo trae columnas que no están en el contrato. Se conservan en
    `extra`, no se descartan (§2)."""

    WEEKDAY_MISMATCH = "weekday_mismatch"
    """El día de la semana declarado en 'Día(s)' no coincide con el que cae
    la fecha. Validación cruzada del §2."""


class ActivityExtraction(BaseModel):
    """Una actividad extraída de una fuente, aún sin publicar.

    Un campo que no aparece en el origen va a `None`. **Está prohibido
    inferir o completar**: si el dato no está, el bot lo dirá.
    """

    model_config = ConfigDict(frozen=True)

    title: str
    venue_slug: str
    starts_at: datetime
    """En UTC. La conversión desde America/Bogota la hace el parser."""

    description: str | None = None
    ends_at: datetime | None = None
    room_id: UUID | None = None
    room_raw: str | None = None
    recurrence: str | None = None

    audience: Audience | None = None
    age_min: int | None = None
    age_max: int | None = None
    audience_raw: str | None = None

    price_amount: int | None = None
    price_currency: str | None = None

    requires_registration: bool | None = None
    """`None` significa «sin resolver»: exige decisión humana (§7)."""
    registration_url: str | None = None

    activity_group_id: UUID | None = None
    """Une las N actividades que salieron de una misma fila con N fechas."""

    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence_snippet: str | None = None
    """La fila original serializada, para que el revisor vea qué se
    interpretó (§9)."""
    source_row: str | None = None
    """Hoja y número de fila de origen."""
    warnings: list[IngestionWarning] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("ends_at")
    @classmethod
    def _end_after_start(cls, value: datetime | None, info: Any) -> datetime | None:
        start = info.data.get("starts_at")
        if value is not None and start is not None and value < start:
            raise ValueError(f"ends_at ({value}) es anterior a starts_at ({start})")
        return value

    @field_validator("age_max")
    @classmethod
    def _age_range(cls, value: int | None, info: Any) -> int | None:
        age_min = info.data.get("age_min")
        if value is not None and age_min is not None and value < age_min:
            raise ValueError(f"age_max ({value}) menor que age_min ({age_min})")
        return value

    @property
    def needs_review(self) -> bool:
        return bool(self.warnings) or self.confidence < 0.8


class RowResult(BaseModel):
    """Resultado de procesar UNA fila del archivo.

    Una fila puede producir varias actividades (N fechas → N actividades),
    o ninguna si tuvo un error.
    """

    model_config = ConfigDict(frozen=True)

    sheet: str
    row_number: int
    status: RowStatus
    extractions: list[ActivityExtraction] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[IngestionWarning] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)

    @property
    def location(self) -> str:
        return f"{self.sheet}!fila {self.row_number}"


class ImportReport(BaseModel):
    """Resumen de una importación completa."""

    model_config = ConfigDict(frozen=True)

    file_name: str
    venue_slug: str
    rows: list[RowResult] = Field(default_factory=list)
    unknown_columns: list[str] = Field(default_factory=list)
    sheets_skipped: list[str] = Field(default_factory=list)
    """Hojas ignoradas por no tener los encabezados esperados. Es un aviso,
    no un error fatal (§1)."""

    @property
    def rows_read(self) -> int:
        return len(self.rows)

    @property
    def rows_ok(self) -> int:
        return sum(1 for r in self.rows if r.status is RowStatus.OK)

    @property
    def rows_warning(self) -> int:
        return sum(1 for r in self.rows if r.status is RowStatus.WARNING)

    @property
    def rows_error(self) -> int:
        return sum(1 for r in self.rows if r.status is RowStatus.ERROR)

    @property
    def extractions(self) -> list[ActivityExtraction]:
        """Todas las actividades, ya expandidas por fecha."""
        return [e for row in self.rows for e in row.extractions]

    @property
    def has_blocking_errors(self) -> bool:
        return self.rows_error > 0

    def render(self) -> str:
        lines = [
            f"{self.file_name} -> {self.venue_slug}",
            f"  {self.rows_read} filas leídas · {self.rows_ok} correctas · "
            f"{self.rows_warning} con advertencia · {self.rows_error} con error",
            f"  {len(self.extractions)} actividades tras expandir fechas",
        ]
        if self.unknown_columns:
            lines.append(f"  columnas desconocidas conservadas: {self.unknown_columns}")
        if self.sheets_skipped:
            lines.append(f"  hojas ignoradas: {self.sheets_skipped}")
        for row in self.rows:
            if row.status is RowStatus.ERROR:
                lines.append(f"  [ERROR] {row.location}: {'; '.join(row.errors)}")
        return "\n".join(lines)
