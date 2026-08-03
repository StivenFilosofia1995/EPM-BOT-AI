"""Contexto acotado `identity`: tenants y usuarios del panel."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from src.domain.entities.enums import TenantStatus, UserRole
from src.domain.value_objects import TenantId


@dataclass(frozen=True, slots=True)
class Tenant:
    """Organización cliente de la plataforma. Raíz del aislamiento: toda
    entidad de negocio cuelga de un tenant (CLAUDE.md §1.2)."""

    id: TenantId
    name: str
    slug: str
    status: TenantStatus
    created_at: datetime
    settings: dict[str, Any] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        return self.status is TenantStatus.ACTIVE


@dataclass(frozen=True, slots=True)
class User:
    """Usuario del panel. La autenticación la resuelve Supabase Auth; aquí
    solo vive el rol dentro del tenant."""

    id: UUID
    tenant_id: TenantId
    email: str
    role: UserRole
    created_at: datetime
    full_name: str | None = None
    is_active: bool = True

    @property
    def can_publish(self) -> bool:
        """Publicar programación es el control de calidad del bot: solo
        `owner` y `admin` (P2B)."""
        return self.role in (UserRole.OWNER, UserRole.ADMIN)

    @property
    def can_reply(self) -> bool:
        return self.role in (UserRole.OWNER, UserRole.ADMIN, UserRole.AGENT)
