"""Contexto acotado `ingestion`: fuentes y corridas de ingesta."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from src.domain.entities.enums import IngestionRunStatus, SourceKind, source_rank
from src.domain.value_objects import TenantId


@dataclass(frozen=True, slots=True)
class Source:
    """Origen de datos de programación o de hechos de espacio.

    La fuente primaria es el Excel interno de la Fundación; las publicadas
    (Issuu, web) son respaldo y verificación (ADR 009).
    """

    id: UUID
    tenant_id: TenantId
    kind: SourceKind
    name: str
    created_at: datetime
    url: str | None = None
    cron: str | None = None
    venue_id: UUID | None = None
    is_active: bool = True
    last_run_at: datetime | None = None

    @property
    def rank(self) -> int:
        """Posición en la precedencia: menor gana en conflicto."""
        return source_rank(self.kind)

    def wins_over(self, other: "Source") -> bool:
        return self.rank < other.rank

    @property
    def is_network_source(self) -> bool:
        """Las fuentes de red respetan robots.txt, timeout y backoff; el Excel
        y la carga manual no salen a internet."""
        return self.kind not in (SourceKind.EXCEL_ADMIN, SourceKind.MANUAL)


@dataclass(frozen=True, slots=True)
class IngestionRun:
    """Una ejecución de ingesta sobre una fuente.

    `content_hash` evita reprocesar contenido idéntico; `stored_file_ref`
    apunta al archivo original guardado en Storage, para poder auditar y
    reprocesar un mes ya publicado.
    """

    id: UUID
    tenant_id: TenantId
    source_id: UUID
    status: IngestionRunStatus
    started_at: datetime
    finished_at: datetime | None = None
    rows_read: int = 0
    rows_imported: int = 0
    rows_warning: int = 0
    rows_error: int = 0
    content_hash: str | None = None
    stored_file_ref: str | None = None
    error: str | None = None
    stats: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float | None:
        if self.finished_at is None:
            return None
        return (self.finished_at - self.started_at).total_seconds()

    @property
    def is_finished(self) -> bool:
        return self.status is not IngestionRunStatus.RUNNING
