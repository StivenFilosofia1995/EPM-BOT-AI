"""Contexto acotado `knowledge`: espacios, salas, hechos y actividades.

Es de donde el bot lee para responder. Nada se consulta por scraping en el
camino caliente de la conversación (CLAUDE.md §3.5).
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from uuid import UUID

from src.domain.entities.enums import PublicationStatus, VenueKind
from src.domain.value_objects import Audience, Confidence, Money, TenantId


@dataclass(frozen=True, slots=True)
class Venue:
    """Espacio físico de la Fundación (KB §3)."""

    id: UUID
    tenant_id: TenantId
    slug: str
    name: str
    kind: VenueKind
    created_at: datetime
    address: str | None = None
    neighborhood: str | None = None
    city: str = "Medellín"
    phones: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    latitude: float | None = None
    longitude: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def has_location(self) -> bool:
        return self.latitude is not None and self.longitude is not None


@dataclass(frozen=True, slots=True)
class Room:
    """Sala dentro de un espacio (contrato de Excel §5).

    El número es significativo: 'Sala de Formación' y 'Sala de Formación 3'
    son salas distintas. Una sala desconocida nunca se crea automáticamente.
    """

    id: UUID
    tenant_id: TenantId
    venue_id: UUID
    name: str
    normalized_name: str
    created_at: datetime
    capacity: int | None = None
    aliases: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class VenueFact:
    """Dato estable de un espacio: horario, tarifa, gratuidad, contacto.

    Versionado por `valid_from`/`valid_to` para poder responder qué era cierto
    en una fecha dada y revalidar mensualmente contra la fuente.
    """

    id: UUID
    tenant_id: TenantId
    venue_id: UUID
    key: str
    value: str
    created_at: datetime
    valid_from: date | None = None
    valid_to: date | None = None
    source_id: UUID | None = None
    source_url: str | None = None
    verified_at: datetime | None = None
    confidence: Confidence = field(default_factory=Confidence.certain)

    def is_valid_on(self, day: date) -> bool:
        if self.valid_from is not None and day < self.valid_from:
            return False
        return not (self.valid_to is not None and day > self.valid_to)


@dataclass(frozen=True, slots=True)
class Activity:
    """Actividad concreta en una fecha y hora.

    Una fila del Excel con N fechas produce N actividades unidas por
    `activity_group_id`, para poder editarlas o borrarlas en bloque desde el
    panel (contrato §3.1).

    `evidence_snippet` guarda el fragmento original del que se extrajo — la
    fila serializada, en el caso del Excel — para que el revisor vea
    exactamente qué se interpretó.
    """

    id: UUID
    tenant_id: TenantId
    venue_id: UUID
    title: str
    starts_at: datetime
    status: PublicationStatus
    created_at: datetime
    description: str | None = None
    ends_at: datetime | None = None
    room_id: UUID | None = None
    room_raw: str | None = None
    recurrence: str | None = None
    audience: Audience | None = None
    age_min: int | None = None
    age_max: int | None = None
    audience_raw: str | None = None
    price: Money | None = None
    requires_registration: bool | None = None
    registration_url: str | None = None
    activity_group_id: UUID | None = None
    source_id: UUID | None = None
    source_url: str | None = None
    source_row: str | None = None
    evidence_snippet: str | None = None
    extracted_at: datetime | None = None
    confidence: Confidence = field(default_factory=Confidence.certain)
    warnings: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)
    published_at: datetime | None = None
    deleted_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.ends_at is not None and self.ends_at < self.starts_at:
            raise ValueError(
                f"La actividad {self.title!r} termina antes de empezar: "
                f"{self.starts_at} → {self.ends_at}"
            )
        if self.age_min is not None and self.age_max is not None and self.age_max < self.age_min:
            raise ValueError(f"Rango de edad invertido en {self.title!r}")

    @property
    def is_published(self) -> bool:
        return self.status is PublicationStatus.PUBLISHED and self.deleted_at is None

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    @property
    def needs_human_review(self) -> bool:
        """Requiere ojo humano si trae advertencias, si la confianza es baja o
        si la inscripción quedó sin resolver (contrato §7)."""
        return (
            bool(self.warnings)
            or self.confidence.is_below(0.8)
            or self.requires_registration is None
        )
