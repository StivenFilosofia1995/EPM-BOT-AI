"""Contexto acotado `conversations`: contactos, conversaciones y mensajes."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from src.domain.entities.enums import (
    ConversationStatus,
    MessageDirection,
    MessageStatus,
    MessageType,
)
from src.domain.value_objects import ConversationWindow, TenantId, WaId, Wamid


@dataclass(frozen=True, slots=True)
class Contact:
    """Persona que escribe al bot.

    `consent_at` y `opt_out_at` implementan el registro de consentimiento y la
    baja que exige la Ley 1581 de 2012 (CLAUDE.md §1.9).
    """

    id: UUID
    tenant_id: TenantId
    wa_id: WaId
    created_at: datetime
    profile_name: str | None = None
    consent_at: datetime | None = None
    opt_out_at: datetime | None = None

    @property
    def has_opted_out(self) -> bool:
        return self.opt_out_at is not None

    @property
    def needs_privacy_notice(self) -> bool:
        """El aviso de privacidad va en el primer mensaje de cada contacto
        nuevo (CLAUDE.md §7)."""
        return self.consent_at is None

    @property
    def can_be_contacted(self) -> bool:
        return not self.has_opted_out


@dataclass(frozen=True, slots=True)
class Conversation:
    """Hilo con un contacto por un canal concreto."""

    id: UUID
    tenant_id: TenantId
    contact_id: UUID
    channel_id: UUID
    status: ConversationStatus
    created_at: datetime
    last_inbound_at: datetime | None = None
    assigned_user_id: UUID | None = None

    @property
    def window(self) -> ConversationWindow:
        return ConversationWindow(last_inbound_at=self.last_inbound_at)

    def can_send_free_text(self, now: datetime) -> bool:
        """Fuera de la ventana solo plantilla; nunca se intenta texto libre."""
        return self.window.is_open(now)

    @property
    def is_escalated(self) -> bool:
        return self.status is ConversationStatus.ESCALATED


@dataclass(frozen=True, slots=True)
class Message:
    """Mensaje entrante o saliente.

    `wamid` es nulo mientras el mensaje está en cola de salida y Meta aún no
    ha devuelto su identificador; en cuanto existe, es único por tenant y
    garantiza la idempotencia (CLAUDE.md §3.4).
    """

    id: UUID
    tenant_id: TenantId
    conversation_id: UUID
    direction: MessageDirection
    type: MessageType
    status: MessageStatus
    created_at: datetime
    wamid: Wamid | None = None
    payload: dict[str, Any] | None = None
    error: str | None = None
    sent_at: datetime | None = None
    delivered_at: datetime | None = None
    read_at: datetime | None = None

    @property
    def is_inbound(self) -> bool:
        return self.direction is MessageDirection.INBOUND

    @property
    def has_failed(self) -> bool:
        return self.status is MessageStatus.FAILED
