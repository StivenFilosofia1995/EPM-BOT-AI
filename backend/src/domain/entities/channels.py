"""Contexto acotado `channels`: cuentas de WhatsApp y plantillas."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from src.domain.entities.enums import ChannelStatus
from src.domain.value_objects import TenantId


@dataclass(frozen=True, slots=True)
class WhatsAppAccount:
    """Número de WhatsApp Business conectado a un tenant.

    `token_ref` es un puntero al secreto cifrado, **nunca el token**
    (CLAUDE.md §4). El `phone_number_id` es la clave por la que se resuelve el
    tenant al recibir un webhook (§3.4): si no resuelve, se descarta el evento.
    """

    id: UUID
    tenant_id: TenantId
    waba_id: str
    phone_number_id: str
    display_number: str
    token_ref: str
    status: ChannelStatus
    created_at: datetime
    verified_name: str | None = None

    @property
    def is_usable(self) -> bool:
        return self.status is ChannelStatus.CONNECTED


@dataclass(frozen=True, slots=True)
class Template:
    """Plantilla aprobada por Meta. Es el único contenido que puede enviarse
    fuera de la ventana de 24 h (CLAUDE.md §3.6)."""

    id: UUID
    tenant_id: TenantId
    name: str
    language: str
    category: str
    status: str
    body: str
    created_at: datetime
    components: dict[str, Any] | None = None

    @property
    def is_approved(self) -> bool:
        return self.status.upper() == "APPROVED"
