"""Tablas de `identity`: tenants y usuarios."""

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


class TenantModel(Base, TimestampMixin):
    """Raíz del aislamiento. Es la única tabla de negocio sin `tenant_id`:
    ella misma es el tenant, y su política de RLS compara contra `id`."""

    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="active")
    settings: Mapped[dict[str, Any]] = mapped_column(nullable=False, server_default="{}")


class UserModel(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        # Un correo puede repetirse entre tenants distintos, nunca dentro del mismo.
        UniqueConstraint("tenant_id", "email", name="uq_users_tenant_id_email"),
        Index("ix_users_tenant_id_role", "tenant_id", "role"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    email: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(200))
    #: Identificador en Supabase Auth. La autenticación no vive aquí.
    auth_user_id: Mapped[uuid.UUID | None] = mapped_column()
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default="true")
