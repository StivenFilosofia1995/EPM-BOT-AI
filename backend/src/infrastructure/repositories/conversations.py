"""Implementación de `ConversationRepositoryPort` sobre SQLAlchemy."""

from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities import (
    Contact,
    Conversation,
    ConversationStatus,
    Message,
    MessageDirection,
    MessageStatus,
    MessageType,
)
from src.domain.ports import ConversationRepositoryPort
from src.domain.value_objects import TenantId, WaId, Wamid
from src.infrastructure.database.models import (
    ContactModel,
    ConversationModel,
    MessageModel,
)
from src.infrastructure.repositories.base import BaseTenantRepository


class SqlAlchemyConversationRepository(BaseTenantRepository, ConversationRepositoryPort):
    """Persistencia de contactos, conversaciones y mensajes.

    El `tenant_id` de la firma de cada método se comprueba contra el del
    repositorio: la interfaz lo exige (CLAUDE.md §1.2) y aquí se verifica que
    ambos coincidan, en vez de confiar en que quien llama pase el correcto.
    """

    def __init__(self, session: AsyncSession, tenant_id: TenantId) -> None:
        super().__init__(session, tenant_id)

    def _check(self, tenant_id: TenantId) -> None:
        if tenant_id != self._tenant_id:
            raise ValueError(
                f"tenant_id del argumento ({tenant_id}) distinto al del "
                f"repositorio ({self._tenant_id})"
            )

    # --- contactos -------------------------------------------------------

    async def get_or_create_contact(
        self, tenant_id: TenantId, wa_id: WaId, *, profile_name: str | None = None
    ) -> Contact:
        self._check(tenant_id)
        stmt = (
            pg_insert(ContactModel)
            .values(**self._with_tenant({"wa_id": str(wa_id), "profile_name": profile_name}))
            # Dos mensajes simultáneos del mismo contacto nuevo no deben
            # crear dos filas: se resuelve en la base, no con un lock.
            .on_conflict_do_update(
                constraint="uq_contacts_tenant_id_wa_id",
                set_={"profile_name": profile_name} if profile_name else {"wa_id": str(wa_id)},
            )
            .returning(ContactModel)
        )
        row = (await self._session.execute(stmt)).scalar_one()
        return self._to_contact(row)

    async def get_contact_by_wa_id(self, tenant_id: TenantId, wa_id: WaId) -> Contact | None:
        self._check(tenant_id)
        stmt = self._scoped(ContactModel).where(ContactModel.wa_id == str(wa_id))
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return self._to_contact(row) if row else None

    # --- conversaciones ---------------------------------------------------

    async def get_or_create_conversation(
        self, tenant_id: TenantId, contact_id: UUID, channel_id: UUID
    ) -> Conversation:
        self._check(tenant_id)
        stmt = (
            self._scoped(ConversationModel)
            .where(ConversationModel.contact_id == contact_id)
            .where(ConversationModel.channel_id == channel_id)
            .where(ConversationModel.status != ConversationStatus.CLOSED.value)
            .order_by(ConversationModel.created_at.desc())
            .limit(1)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            row = ConversationModel(
                **self._with_tenant(
                    {
                        "contact_id": contact_id,
                        "channel_id": channel_id,
                        "status": ConversationStatus.OPEN.value,
                    }
                )
            )
            self._session.add(row)
            await self._session.flush()
        return self._to_conversation(row)

    async def get_conversation(
        self, tenant_id: TenantId, conversation_id: UUID
    ) -> Conversation | None:
        self._check(tenant_id)
        stmt = self._scoped(ConversationModel).where(ConversationModel.id == conversation_id)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return self._to_conversation(row) if row else None

    async def touch_inbound(
        self, tenant_id: TenantId, conversation_id: UUID, *, occurred_at: datetime
    ) -> None:
        self._check(tenant_id)
        await self._session.execute(
            update(ConversationModel)
            .where(ConversationModel.tenant_id == self._tenant_id.value)
            .where(ConversationModel.id == conversation_id)
            .values(last_inbound_at=occurred_at)
        )

    # --- mensajes ---------------------------------------------------------

    async def add_message(self, tenant_id: TenantId, message: Message) -> Message:
        self._check(tenant_id)
        values = self._with_tenant(
            {
                "conversation_id": message.conversation_id,
                "wamid": str(message.wamid) if message.wamid else None,
                "direction": message.direction.value,
                "type": message.type.value,
                "status": message.status.value,
                "payload": message.payload,
                "error": message.error,
            }
        )
        if message.wamid is None:
            row = MessageModel(**values)
            self._session.add(row)
            await self._session.flush()
            return self._to_message(row)

        # Con wamid: idempotente. Un reintento de Meta no genera doble fila ni
        # doble respuesta (CLAUDE.md §3.4).
        stmt = (
            pg_insert(MessageModel)
            .values(**values)
            .on_conflict_do_nothing(index_elements=["tenant_id", "wamid"])
            .returning(MessageModel)
        )
        inserted = (await self._session.execute(stmt)).scalar_one_or_none()
        if inserted is not None:
            return self._to_message(inserted)

        existing = (
            await self._session.execute(
                self._scoped(MessageModel).where(MessageModel.wamid == str(message.wamid))
            )
        ).scalar_one()
        return self._to_message(existing)

    async def message_exists(self, tenant_id: TenantId, wamid: Wamid) -> bool:
        self._check(tenant_id)
        stmt = self._scoped(MessageModel).where(MessageModel.wamid == str(wamid)).limit(1)
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def update_message_status(
        self,
        tenant_id: TenantId,
        wamid: Wamid,
        status: str,
        *,
        occurred_at: datetime,
        error: str | None = None,
    ) -> bool:
        self._check(tenant_id)
        timestamp_column = {
            MessageStatus.SENT.value: "sent_at",
            MessageStatus.DELIVERED.value: "delivered_at",
            MessageStatus.READ.value: "read_at",
        }.get(status)

        values: dict[str, object] = {"status": status}
        if timestamp_column:
            values[timestamp_column] = occurred_at
        if error is not None:
            values["error"] = error

        # `execute` de un UPDATE devuelve un CursorResult, que es quien tiene
        # `rowcount`; el tipo declarado de `execute` es el Result genérico.
        result = cast(
            "CursorResult[Any]",
            await self._session.execute(
                update(MessageModel)
                .where(MessageModel.tenant_id == self._tenant_id.value)
                .where(MessageModel.wamid == str(wamid))
                .values(**values)
            ),
        )
        # False cuando el wamid no existe: un evento de estado de un mensaje
        # que no es nuestro se ignora en silencio, no revienta el webhook.
        return bool(result.rowcount)

    async def list_recent_messages(
        self, tenant_id: TenantId, conversation_id: UUID, *, limit: int = 20
    ) -> list[Message]:
        self._check(tenant_id)
        stmt = (
            self._scoped(MessageModel)
            .where(MessageModel.conversation_id == conversation_id)
            .order_by(MessageModel.created_at.desc())
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        # Se devuelven en orden cronológico: es como los espera el prompt.
        return [self._to_message(row) for row in reversed(rows)]

    # --- traducción modelo -> entidad -------------------------------------

    def _to_contact(self, row: ContactModel) -> Contact:
        return Contact(
            id=row.id,
            tenant_id=TenantId(row.tenant_id),
            wa_id=WaId(row.wa_id),
            profile_name=row.profile_name,
            consent_at=row.consent_at,
            opt_out_at=row.opt_out_at,
            created_at=row.created_at,
        )

    def _to_conversation(self, row: ConversationModel) -> Conversation:
        return Conversation(
            id=row.id,
            tenant_id=TenantId(row.tenant_id),
            contact_id=row.contact_id,
            channel_id=row.channel_id,
            status=ConversationStatus(row.status),
            last_inbound_at=row.last_inbound_at,
            assigned_user_id=row.assigned_user_id,
            created_at=row.created_at,
        )

    def _to_message(self, row: MessageModel) -> Message:
        return Message(
            id=row.id,
            tenant_id=TenantId(row.tenant_id),
            conversation_id=row.conversation_id,
            wamid=Wamid(row.wamid) if row.wamid else None,
            direction=MessageDirection(row.direction),
            type=MessageType(row.type),
            status=MessageStatus(row.status),
            payload=row.payload,
            error=row.error,
            sent_at=row.sent_at,
            delivered_at=row.delivered_at,
            read_at=row.read_at,
            created_at=row.created_at,
        )
