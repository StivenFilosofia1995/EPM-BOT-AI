"""Tablas de `ingestion`, `ai` y `audit`."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base import (
    Base,
    TimestampMixin,
    tenant_fk,
    uuid_pk,
)


class SourceModel(Base, TimestampMixin):
    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_sources_tenant_id_name"),
        Index("ix_sources_tenant_id_kind", "tenant_id", "kind"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    #: excel_admin | manual | pdf_issuu | venue_page | web_programacion | news.
    #: La precedencia en conflicto vive en el dominio (ADR 009), no aquí.
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    cron: Mapped[str | None] = mapped_column(String(80))
    venue_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("venues.id", ondelete="CASCADE")
    )
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default="true")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IngestionRunModel(Base, TimestampMixin):
    __tablename__ = "ingestion_runs"
    __table_args__ = (
        Index("ix_ingestion_runs_tenant_id_source_id_started_at",
              "tenant_id", "source_id", "started_at"),
        # Evita reprocesar contenido idéntico de la misma fuente (P2A §6).
        Index("ix_ingestion_runs_tenant_id_content_hash", "tenant_id", "content_hash"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    source_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rows_read: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    rows_imported: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    rows_warning: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    rows_error: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    content_hash: Mapped[str | None] = mapped_column(String(64))
    #: Ruta del archivo original en Supabase Storage, para auditar y reprocesar.
    stored_file_ref: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    stats: Mapped[dict[str, Any]] = mapped_column(nullable=False, server_default="{}")


class AITraceModel(Base, TimestampMixin):
    """Traza de cada llamada al proveedor de IA: consumo, latencia y coste."""

    __tablename__ = "ai_traces"
    __table_args__ = (
        Index("ix_ai_traces_tenant_id_created_at", "tenant_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL")
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    cost_estimate_usd: Mapped[float | None] = mapped_column(Float)
    intent: Mapped[str | None] = mapped_column(String(40))
    #: Cuántas veces se rechazó la respuesta por el guardarraíl
    #: anti-alucinación antes de aceptarla (P3 §6).
    guardrail_retries: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class AuditLogModel(Base, TimestampMixin):
    """Registro de acciones sobre datos. Toda acción destructiva del panel
    pasa por aquí (P2B §6)."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_tenant_id_entity_entity_id", "tenant_id", "entity", "entity_id"),
        Index("ix_audit_logs_tenant_id_created_at", "tenant_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    entity: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    #: Diferencia campo a campo, que es lo que alimenta el historial de P2B §5.
    diff: Mapped[dict[str, Any]] = mapped_column(nullable=False, server_default="{}")
