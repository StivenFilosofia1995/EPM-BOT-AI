"""Recepción de un mensaje entrante de WhatsApp.

Este caso de uso solo **recibe y guarda**. No responde: redactar la respuesta
necesita el motor de IA, que llega en P3. Separarlo es deliberado — así el
webhook puede entrar en producción y empezar a acumular conversaciones reales
antes de que exista el bot, y cuando el bot llegue ya hay historial.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.value_objects import TenantId, WaId
from src.infrastructure.database.session import tenant_session

logger = structlog.get_logger()


@dataclass(frozen=True)
class InboundMessage:
    """Un mensaje entrante ya extraído del sobre del webhook."""

    wamid: str
    wa_id: str
    phone_number_id: str
    type: str
    text: str | None
    timestamp: datetime
    profile_name: str | None
    raw: dict[str, Any]


def parse_webhook(payload: dict[str, Any]) -> list[InboundMessage]:
    """Extrae los mensajes de un evento de Meta.

    El sobre de Meta anida cuatro niveles y puede traer varios mensajes en una
    sola entrega. Además llegan eventos que **no** son mensajes (acuses de
    entrega, cambios de plantilla): se ignoran en silencio en vez de fallar,
    porque suscribirse a un campo implica recibir todo lo suyo.
    """
    messages: list[InboundMessage] = []

    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            metadata = value.get("metadata") or {}
            phone_number_id = str(metadata.get("phone_number_id") or "")

            # El nombre del perfil viene en un bloque aparte, indexado por wa_id.
            profiles = {
                str(c.get("wa_id")): ((c.get("profile") or {}).get("name"))
                for c in (value.get("contacts") or [])
            }

            for message in value.get("messages") or []:
                wamid = str(message.get("id") or "")
                wa_id = str(message.get("from") or "")
                if not wamid or not wa_id:
                    continue

                kind = str(message.get("type") or "unknown")
                body = None
                if kind == "text":
                    body = (message.get("text") or {}).get("body")

                # Meta manda el instante como epoch en segundos, en texto.
                try:
                    when = datetime.fromtimestamp(int(message["timestamp"]), UTC)
                except (KeyError, ValueError, TypeError):
                    when = datetime.now(UTC)

                messages.append(
                    InboundMessage(
                        wamid=wamid,
                        wa_id=wa_id,
                        phone_number_id=phone_number_id,
                        type=kind,
                        text=body,
                        timestamp=when,
                        profile_name=profiles.get(wa_id),
                        raw=message,
                    )
                )

    return messages


async def _resolve_contact(
    session: AsyncSession, tenant_id: TenantId, message: InboundMessage
) -> uuid.UUID:
    """Contacto del remitente, creándolo si es la primera vez que escribe."""
    existing = await session.scalar(
        text("SELECT id FROM contacts WHERE wa_id = :wa_id"),
        {"wa_id": message.wa_id},
    )
    if existing is not None:
        # El nombre de perfil puede cambiar; se refresca si Meta lo manda.
        if message.profile_name:
            await session.execute(
                text("UPDATE contacts SET profile_name = :name WHERE id = :id"),
                {"name": message.profile_name, "id": existing},
            )
        return uuid.UUID(str(existing))

    created = await session.scalar(
        text(
            "INSERT INTO contacts (tenant_id, wa_id, profile_name)"
            " VALUES (:tenant_id, :wa_id, :name) RETURNING id"
        ),
        {
            "tenant_id": str(tenant_id),
            "wa_id": message.wa_id,
            "name": message.profile_name,
        },
    )
    return uuid.UUID(str(created))


async def _resolve_conversation(
    session: AsyncSession,
    tenant_id: TenantId,
    contact_id: uuid.UUID,
    channel_id: uuid.UUID,
    message: InboundMessage,
) -> uuid.UUID:
    """Conversación abierta del contacto, o una nueva.

    Cada mensaje entrante reabre la ventana de servicio de 24 h (CLAUDE.md
    §3.6). Lo único que se guarda es `last_inbound_at`: el vencimiento **no**
    se almacena, se deriva con `ConversationWindow` en el dominio. Es la
    decisión de P1 y evita que existan dos verdades sobre si la ventana está
    abierta — una columna que puede quedar desfasada y una regla de negocio.
    """
    existing = await session.scalar(
        text(
            "SELECT id FROM conversations"
            " WHERE contact_id = :contact_id AND status = 'open'"
            " ORDER BY created_at DESC LIMIT 1"
        ),
        {"contact_id": str(contact_id)},
    )
    if existing is not None:
        await session.execute(
            text("UPDATE conversations SET last_inbound_at = :at WHERE id = :id"),
            {"at": message.timestamp, "id": existing},
        )
        return uuid.UUID(str(existing))

    created = await session.scalar(
        text(
            "INSERT INTO conversations"
            " (tenant_id, contact_id, channel_id, status, last_inbound_at)"
            " VALUES (:tenant_id, :contact_id, :channel_id, 'open', :at)"
            " RETURNING id"
        ),
        {
            "tenant_id": str(tenant_id),
            "contact_id": str(contact_id),
            "channel_id": str(channel_id),
            "at": message.timestamp,
        },
    )
    return uuid.UUID(str(created))


async def store_inbound_message(
    *,
    tenant_id: TenantId,
    channel_id: uuid.UUID,
    message: InboundMessage,
) -> bool:
    """Guarda un mensaje entrante. Devuelve `False` si ya estaba.

    **Idempotente por `wamid`.** Meta reintenta la entrega cuando no recibe un
    200 a tiempo, así que el mismo mensaje puede llegar varias veces. Sin esto,
    un reintento crearía un duplicado y —cuando exista el bot— provocaría una
    segunda respuesta al usuario.
    """
    # Se valida aquí para que un `from` malformado no llegue a la base.
    wa_id = WaId.parse(message.wa_id)

    async with tenant_session(tenant_id) as session:
        already = await session.scalar(
            text("SELECT 1 FROM messages WHERE wamid = :wamid"),
            {"wamid": message.wamid},
        )
        if already is not None:
            logger.info(
                "webhook_duplicate_ignored",
                wamid=message.wamid,
                wa_id=wa_id.masked,
            )
            return False

        contact_id = await _resolve_contact(session, tenant_id, message)
        conversation_id = await _resolve_conversation(
            session, tenant_id, contact_id, channel_id, message
        )

        await session.execute(
            text(
                "INSERT INTO messages"
                " (tenant_id, conversation_id, wamid, direction, type, status,"
                "  payload)"
                " VALUES (:tenant_id, :conversation_id, :wamid, 'inbound', :type,"
                "         'received', CAST(:payload AS jsonb))"
            ),
            {
                "tenant_id": str(tenant_id),
                "conversation_id": str(conversation_id),
                "wamid": message.wamid,
                "type": message.type,
                "payload": _as_json(message.raw),
            },
        )

    logger.info(
        "webhook_message_stored",
        wamid=message.wamid,
        wa_id=wa_id.masked,  # nunca el número en claro (CLAUDE.md §8)
        type=message.type,
    )
    return True


def _as_json(value: dict[str, Any]) -> str:
    import json  # noqa: PLC0415

    return json.dumps(value, ensure_ascii=False)
