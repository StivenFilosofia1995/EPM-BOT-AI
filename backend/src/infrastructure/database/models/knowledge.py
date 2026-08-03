"""Tablas de `knowledge`: espacios, salas, hechos y actividades.

Es la fuente de la que el bot lee para responder. Nada llega aquí en estado
`published` sin que una persona lo apruebe (ADR 005).
"""

import uuid
from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base import (
    EMBEDDING_DIM,
    Base,
    TimestampMixin,
    tenant_fk,
    uuid_pk,
)


class VenueModel(Base, TimestampMixin):
    __tablename__ = "venues"
    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="uq_venues_tenant_id_slug"),
        Index("ix_venues_tenant_id_kind", "tenant_id", "kind"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    neighborhood: Mapped[str | None] = mapped_column(String(120))
    city: Mapped[str] = mapped_column(String(120), nullable=False, server_default="Medellín")
    phones: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    emails: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", nullable=False, server_default="{}"
    )


class RoomModel(Base, TimestampMixin):
    """Catálogo de salas por espacio (contrato de Excel §5).

    `normalized_name` es el nombre en minúsculas y sin tildes, que es contra lo
    que el importador hace la coincidencia difusa. El número es significativo:
    'sala de formacion' y 'sala de formacion 3' son filas distintas.
    """

    __tablename__ = "rooms"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "venue_id", "normalized_name", name="uq_rooms_tenant_id_venue_id_norm"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    venue_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("venues.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False)
    capacity: Mapped[int | None] = mapped_column(Integer)
    aliases: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )


class VenueFactModel(Base, TimestampMixin):
    """Dato estable de un espacio, versionado por vigencia."""

    __tablename__ = "venue_facts"
    __table_args__ = (
        Index("ix_venue_facts_tenant_id_venue_id_key", "tenant_id", "venue_id", "key"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    venue_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("venues.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("sources.id", ondelete="SET NULL")
    )
    #: Un dato sin fuente no entra a la base (KB, regla de oro).
    source_url: Mapped[str | None] = mapped_column(Text)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default="1.0")


class ActivityModel(Base, TimestampMixin):
    """Actividad en una fecha y hora concretas.

    Una fila de Excel con N fechas produce N actividades unidas por
    `activity_group_id` (contrato §3.1).
    """

    __tablename__ = "activities"
    __table_args__ = (
        # Índice principal de recuperación: el filtro duro del bot es
        # tenant + espacio + rango de fechas (ADR 006).
        Index("ix_activities_tenant_id_venue_id_starts_at", "tenant_id", "venue_id", "starts_at"),
        Index("ix_activities_tenant_id_status_starts_at", "tenant_id", "status", "starts_at"),
        Index("ix_activities_tenant_id_activity_group_id", "tenant_id", "activity_group_id"),
        # Deduplicación del pipeline: mismo espacio, mismo título normalizado y
        # misma hora es la misma actividad (P2A §4). Parcial para que las
        # borradas no bloqueen una recarga.
        Index(
            "uq_activities_dedupe",
            "tenant_id",
            "venue_id",
            "normalized_title",
            "starts_at",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    venue_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("venues.id", ondelete="CASCADE"), nullable=False
    )
    room_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("rooms.id", ondelete="SET NULL")
    )
    #: Texto original de la sala cuando no se pudo resolver contra el catálogo.
    room_raw: Mapped[str | None] = mapped_column(String(200))

    title: Mapped[str] = mapped_column(Text, nullable=False)
    #: Título en minúsculas y sin tildes; solo para deduplicar.
    normalized_title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recurrence: Mapped[str | None] = mapped_column(String(200))
    activity_group_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))

    audience: Mapped[str | None] = mapped_column(String(20))
    age_min: Mapped[int | None] = mapped_column(Integer)
    age_max: Mapped[int | None] = mapped_column(Integer)
    #: Texto literal del público, para mostrarlo tal cual al usuario (§6).
    audience_raw: Mapped[str | None] = mapped_column(Text)

    #: Importe en la unidad mínima. NULL = desconocido, 0 = gratis.
    price_amount: Mapped[int | None] = mapped_column(Numeric(12, 0))
    price_currency: Mapped[str | None] = mapped_column(String(3))

    #: NULL significa «sin resolver»: exige decisión humana, no se asume nada
    #: (contrato §7).
    requires_registration: Mapped[bool | None] = mapped_column()
    registration_url: Mapped[str | None] = mapped_column(Text)

    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="draft")
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("sources.id", ondelete="SET NULL")
    )
    source_url: Mapped[str | None] = mapped_column(Text)
    #: Hoja y número de fila de origen, para poder rastrear el dato.
    source_row: Mapped[str | None] = mapped_column(String(120))
    #: Fragmento original del que se extrajo: la fila serializada en el caso
    #: del Excel. Es lo que ve el revisor al lado del JSON estructurado (P2B).
    evidence_snippet: Mapped[str | None] = mapped_column(Text)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default="1.0")
    warnings: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    #: Columnas desconocidas del Excel: se conservan, no se descartan (§2).
    extra: Mapped[dict[str, Any]] = mapped_column(nullable=False, server_default="{}")

    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    #: Soft delete con papelera de 30 días (P2B §2).
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ActivityEmbeddingModel(Base, TimestampMixin):
    """Embedding para el re-ranking semántico.

    Lleva `tenant_id` propio aunque sea derivable de la actividad: sin él no se
    le puede aplicar RLS, y una tabla sin RLS es una fuga.
    """

    __tablename__ = "activity_embeddings"

    activity_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("activities.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
