"""Puertos de persistencia.

Regla innegociable: **ningún método puede existir sin `tenant_id`**
(CLAUDE.md §1.2). El test `tests/unit/test_ports_require_tenant.py` lo verifica
inspeccionando las firmas, para que no dependa de la disciplina de quien
escriba el siguiente repositorio.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from src.domain.entities import Contact, Conversation, Message
from src.domain.value_objects import TenantId, WaId, Wamid


class ConversationRepositoryPort(ABC):
    """Persistencia de contactos, conversaciones y mensajes."""

    @abstractmethod
    async def get_or_create_contact(
        self, tenant_id: TenantId, wa_id: WaId, *, profile_name: str | None = None
    ) -> Contact:
        """Devuelve el contacto, creándolo si es su primer mensaje."""

    @abstractmethod
    async def get_contact_by_wa_id(self, tenant_id: TenantId, wa_id: WaId) -> Contact | None: ...

    @abstractmethod
    async def mark_privacy_notice_sent(
        self, tenant_id: TenantId, contact_id: UUID, *, occurred_at: datetime
    ) -> None:
        """Registra `consent_at`, para no repetir el aviso de privacidad en
        cada mensaje del mismo contacto (CLAUDE.md §7, Ley 1581 de 2012)."""

    @abstractmethod
    async def get_or_create_conversation(
        self, tenant_id: TenantId, contact_id: UUID, channel_id: UUID
    ) -> Conversation: ...

    @abstractmethod
    async def get_conversation(
        self, tenant_id: TenantId, conversation_id: UUID
    ) -> Conversation | None: ...

    @abstractmethod
    async def add_message(self, tenant_id: TenantId, message: Message) -> Message:
        """Persiste un mensaje. Si el `wamid` ya existe para el tenant, no
        duplica: devuelve el existente (idempotencia, CLAUDE.md §3.4)."""

    @abstractmethod
    async def message_exists(self, tenant_id: TenantId, wamid: Wamid) -> bool: ...

    @abstractmethod
    async def update_message_status(
        self,
        tenant_id: TenantId,
        wamid: Wamid,
        status: str,
        *,
        occurred_at: datetime,
        error: str | None = None,
    ) -> bool:
        """Aplica un evento de estado de Meta (sent/delivered/read/failed)."""

    @abstractmethod
    async def list_recent_messages(
        self, tenant_id: TenantId, conversation_id: UUID, *, limit: int = 20
    ) -> list[Message]:
        """Historial reciente, para construir el contexto de la respuesta."""

    @abstractmethod
    async def touch_inbound(
        self, tenant_id: TenantId, conversation_id: UUID, *, occurred_at: datetime
    ) -> None:
        """Actualiza `last_inbound_at`, que es lo que abre la ventana de 24 h."""
