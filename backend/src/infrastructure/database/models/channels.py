"""Tablas de `channels`: cuentas de WhatsApp y plantillas."""

import uuid
from typing import Any

from sqlalchemy import Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base import (
    Base,
    TimestampMixin,
    tenant_fk,
    uuid_pk,
)


class WhatsAppAccountModel(Base, TimestampMixin):
    __tablename__ = "whatsapp_accounts"
    __table_args__ = (
        # `phone_number_id` es global de Meta: un número solo puede pertenecer a
        # un tenant. Esta restricción es lo que hace segura la resolución de
        # tenant en el webhook (CLAUDE.md §3.4).
        UniqueConstraint("phone_number_id", name="uq_whatsapp_accounts_phone_number_id"),
        Index("ix_whatsapp_accounts_tenant_id_status", "tenant_id", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    waba_id: Mapped[str] = mapped_column(String(64), nullable=False)
    phone_number_id: Mapped[str] = mapped_column(String(64), nullable=False)
    display_number: Mapped[str] = mapped_column(String(32), nullable=False)
    verified_name: Mapped[str | None] = mapped_column(String(200))
    #: Puntero al secreto cifrado, NUNCA el token (CLAUDE.md §4).
    token_ref: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")


class TemplateModel(Base, TimestampMixin):
    __tablename__ = "templates"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "name", "language", name="uq_templates_tenant_id_name_language"
        ),
        Index("ix_templates_tenant_id_status", "tenant_id", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    components: Mapped[dict[str, Any] | None] = mapped_column()
