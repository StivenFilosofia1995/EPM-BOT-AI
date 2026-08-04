"""Orquesta la respuesta a un mensaje de texto entrante.

Recupera conocimiento ya publicado, le pide a la IA que redacte con eso y
solo eso, valida el resultado y lo manda de vuelta. Nada de esto decide qué
proveedor de IA o de mensajería usar: eso lo inyecta quien llama (hoy,
`presentation/routers/webhooks.py`), siguiendo el patrón puerto/adaptador
(CLAUDE.md §2, ADR 002 y 004).

**Simplificación deliberada de esta primera versión** (ver también
`infrastructure/knowledge/sql_knowledge_retriever.py`): la detección de
espacio/fecha/audiencia mencionados en el mensaje no existe todavía — se le
pasa el texto crudo del usuario como filtro de `ActivityQuery.text`. Es
suficiente para no alucinar (el modelo solo ve actividades reales), pero
puede no encontrar candidatos cuando la pregunta no comparte palabras con el
título de la actividad. Clasificar intención queda para una iteración
siguiente.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import structlog

from src.domain.entities import Activity, Message, MessageDirection, MessageStatus, MessageType
from src.domain.ports.ai_provider import AIMessage, AIProviderPort, AIRole
from src.domain.ports.knowledge import ActivityQuery, KnowledgeRetrieverPort
from src.domain.ports.messaging import MessagingPort
from src.domain.ports.repositories import ConversationRepositoryPort
from src.domain.value_objects import TenantId, WaId
from src.infrastructure.database.session import tenant_session
from src.infrastructure.repositories.conversations import SqlAlchemyConversationRepository

logger = structlog.get_logger()

#: CLAUDE.md §7: máximo ~600 caracteres por mensaje de WhatsApp.
MAX_REPLY_CHARS = 600

#: CLAUDE.md §7: disparadores de escalamiento a humano. Coincidencia simple
#: por palabra clave — una clasificación real de intención queda pendiente.
_ESCALATION_KEYWORDS = (
    "queja",
    "pqrsdf",
    "reclamo",
    "hablar con un asesor",
    "hablar con una persona",
    "quiero un humano",
    "asesor humano",
    "denuncia",
)

_PRIVACY_NOTICE = (
    "Antes de seguir: usamos tu número y tus mensajes solo para responder tu "
    "consulta sobre la programación cultural de la Fundación Grupo EPM, "
    "según la Ley 1581 de 2012. Más info: "
    "https://epm-bot-ai-production-e43d.up.railway.app/privacidad\n\n"
)

_ESCALATION_REPLY = (
    "Entiendo. Te voy a comunicar con una persona del equipo para que te "
    "ayude con esto — en un momento te contactan por este mismo chat."
)

SYSTEM_PROMPT = """\
Sos el asistente de WhatsApp de la Fundación Grupo EPM (Biblioteca EPM, \
Museo del Agua, Parque de los Deseos / Casa de la Música y las UVA). \
Tuteás, español de Colombia, cordial y breve.

Podés: informar programación, horarios, tarifas, direcciones, requisitos de \
ingreso, gratuidades, cómo llegar; entregar enlaces oficiales de reserva o \
inscripción.

NO podés: inventar actividades, fechas o precios que no estén en el \
contexto de abajo; confirmar reservas o cupos; atender facturación o \
servicios públicos de EPM (la Fundación no es EPM, hay que derivar); dar \
datos de las 4 UVA operadas por el INDER; prometer disponibilidad.

Si el contexto no trae el dato que te piden, decilo explícitamente y \
ofrecé el canal oficial del espacio. Nunca rellenes con lo que "sabés" por \
tu cuenta: solo con lo que está en el contexto.

Formato: máximo ~600 caracteres, máximo 5 actividades, cada una como \
"*Título* — día, hora · público · lugar". Cerrá con una pregunta útil o un \
enlace."""


def _needs_escalation(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in _ESCALATION_KEYWORDS)


def _extract_text(message: Message) -> str | None:
    """Texto de un mensaje ya guardado, para reconstruir el historial.

    Los entrantes guardan el sobre crudo de Meta; los salientes, lo que este
    mismo módulo escribió. Un mensaje sin texto (imagen, plantilla) se omite
    del contexto en vez de fallar.
    """
    if not message.payload:
        return None
    if message.direction is MessageDirection.OUTBOUND:
        text = message.payload.get("text")
        return text if isinstance(text, str) else None
    body = (message.payload.get("text") or {}).get("body")
    return body if isinstance(body, str) else None


def _build_ai_messages(history: list[Message], inbound_text: str) -> list[AIMessage]:
    messages = []
    for past in history:
        text = _extract_text(past)
        if text is None:
            continue
        role = AIRole.ASSISTANT if past.direction is MessageDirection.OUTBOUND else AIRole.USER
        messages.append(AIMessage(role=role, content=text))
    messages.append(AIMessage(role=AIRole.USER, content=inbound_text))
    return messages


def _format_activities_for_prompt(activities: list[Activity]) -> str:
    if not activities:
        return "No hay actividades publicadas que coincidan con la consulta."
    lines = []
    for activity in activities:
        price = activity.price.format_es_co() if activity.price else "sin dato de tarifa"
        audience = activity.audience.value if activity.audience else "sin dato"
        registration = (
            f" · inscripción: {activity.registration_url}" if activity.registration_url else ""
        )
        lines.append(
            f"- {activity.title} — {activity.starts_at.isoformat()} · "
            f"audiencia: {audience} · {price}{registration}"
        )
    return "\n".join(lines)


async def respond_to_inbound_message(
    *,
    tenant_id: TenantId,
    channel_id: UUID,
    wa_id: WaId,
    profile_name: str | None,
    inbound_text: str,
    ai_provider: AIProviderPort,
    messaging: MessagingPort,
    knowledge: KnowledgeRetrieverPort,
) -> None:
    """Responde un mensaje de texto entrante ya guardado por el webhook.

    No lanza: cualquier fallo se registra y se traga, porque el webhook que
    llama a esto ya le respondió 200 a Meta y no puede permitir que un error
    de la IA o del envío tumbe el proceso (CLAUDE.md §3.4).
    """
    now = datetime.now(UTC)

    async with tenant_session(tenant_id) as session:
        repo: ConversationRepositoryPort = SqlAlchemyConversationRepository(session, tenant_id)
        contact = await repo.get_or_create_contact(tenant_id, wa_id, profile_name=profile_name)
        if contact.has_opted_out:
            logger.info("respond_skipped_opted_out", tenant_id=str(tenant_id))
            return

        conversation = await repo.get_or_create_conversation(tenant_id, contact.id, channel_id)
        history = await repo.list_recent_messages(tenant_id, conversation.id, limit=10)
        needs_notice = contact.needs_privacy_notice

    if not conversation.can_send_free_text(now):
        # No debería pasar: el mensaje entrante que disparó esto acaba de
        # abrir la ventana. Se registra porque indicaría un reloj desfasado
        # o un bug en `touch_inbound`, no un caso de negocio esperado.
        logger.warning("respond_skipped_window_closed", tenant_id=str(tenant_id))
        return

    activities = await knowledge.find_activities(
        ActivityQuery(tenant_id=tenant_id, text=inbound_text, limit=5)
    )
    context = _format_activities_for_prompt(list(activities))

    escalate = _needs_escalation(inbound_text)
    ai_messages = _build_ai_messages(history, inbound_text)

    if escalate:
        reply_text = _ESCALATION_REPLY
    else:
        system_prompt = (
            f"{SYSTEM_PROMPT}\n\nContexto recuperado (lo único real disponible):\n{context}"
        )
        ai_response = await ai_provider.complete(
            tenant_id,
            ai_messages,
            system=system_prompt,
            max_tokens=400,
        )
        reply_text = ai_response.text.strip()[:MAX_REPLY_CHARS]

    if needs_notice:
        reply_text = _PRIVACY_NOTICE + reply_text

    result = await messaging.send_text(tenant_id, wa_id, reply_text)
    if not result.accepted:
        logger.error(
            "respond_send_failed",
            tenant_id=str(tenant_id),
            error_code=result.error_code,
            error_message=result.error_message,
        )

    async with tenant_session(tenant_id) as session:
        repo = SqlAlchemyConversationRepository(session, tenant_id)
        await repo.add_message(
            tenant_id,
            Message(
                id=uuid4(),
                tenant_id=tenant_id,
                conversation_id=conversation.id,
                wamid=result.wamid,
                direction=MessageDirection.OUTBOUND,
                type=MessageType.TEXT,
                status=MessageStatus.SENT if result.accepted else MessageStatus.FAILED,
                payload={"text": reply_text},
                error=result.error_message,
                created_at=now,
            ),
        )
        if needs_notice and result.accepted:
            await repo.mark_privacy_notice_sent(tenant_id, contact.id, occurred_at=now)

    if escalate:
        logger.info("respond_escalated", tenant_id=str(tenant_id))
