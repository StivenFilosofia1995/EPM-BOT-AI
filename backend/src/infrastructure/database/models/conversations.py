"""Tablas de `conversations`: contactos, conversaciones y mensajes."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base import (
    Base,
    TimestampMixin,
    tenant_fk,
    uuid_pk,
)


class ContactModel(Base, TimestampMixin):
    __tablename__ = "contacts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "wa_id", name="uq_contacts_tenant_id_wa_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    #: E.164 con '+'. En logs va enmascarado (CLAUDE.md §8).
    wa_id: Mapped[str] = mapped_column(String(20), nullable=False)
    profile_name: Mapped[str | None] = mapped_column(String(200))
    #: Consentimiento y baja: Ley 1581 de 2012 (CLAUDE.md §1.9).
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    opt_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConversationModel(Base, TimestampMixin):
    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_tenant_id_status", "tenant_id", "status"),
        # Ordenar la bandeja por actividad reciente dentro del tenant.
        Index(
            "ix_conversations_tenant_id_last_inbound_at",
            "tenant_id",
            "last_inbound_at",
            postgresql_using="btree",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    contact_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("whatsapp_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="open")
    #: Abre la ventana de 24 h. `window_expires_at` no se almacena: se deriva
    #: del dominio (`ConversationWindow`) para que no haya dos verdades.
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class MessageModel(Base, TimestampMixin):
    __tablename__ = "messages"
    __table_args__ = (
        # Índice ÚNICO PARCIAL: el wamid es único por tenant, pero solo cuando
        # existe. Un mensaje saliente en cola aún no tiene wamid y varios NULL
        # no deben colisionar. Esta es la garantía de idempotencia en base de
        # datos que respalda al SETNX de Redis (CLAUDE.md §3.4).
        Index(
            "uq_messages_tenant_id_wamid",
            "tenant_id",
            "wamid",
            unique=True,
            postgresql_where=text("wamid IS NOT NULL"),
        ),
        Index(
            "ix_messages_tenant_id_conversation_id_created_at",
            "tenant_id",
            "conversation_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    wamid: Mapped[str | None] = mapped_column(String(128))
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    #: Contenido del mensaje. Se cifra en reposo y tiene retención definida
    #: (CLAUDE.md §8, ADR 008) — el cifrado se implementa en P6.
    payload: Mapped[dict[str, Any] | None] = mapped_column()
    error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
