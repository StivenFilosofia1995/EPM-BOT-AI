"""Webhook de WhatsApp Cloud API.

Dos verbos con propósitos distintos:

- `GET`  — el apretón de manos. Meta lo llama una sola vez, al guardar la
  configuración, para comprobar que la URL es nuestra.
- `POST` — la entrega de eventos. Se verifica la firma, se responde 200 de
  inmediato y se guarda el mensaje.

**Siempre se responde 200 al POST**, incluso si algo falla al guardar. Meta
reintenta cuando no recibe 200 a tiempo y, tras varios fallos, desactiva la
suscripción entera (CLAUDE.md §3.4). Un error nuestro no puede costar el canal:
se registra y se sigue. La única excepción es la firma inválida, que se rechaza
con 403 porque no viene de Meta.
"""

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import text

from src.application.messaging.receive_inbound import parse_webhook, store_inbound_message
from src.config.settings import get_settings
from src.domain.value_objects import TenantId
from src.infrastructure.meta.signature import is_valid_signature

logger = structlog.get_logger()

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.get("/whatsapp", response_class=PlainTextResponse)
async def verify_webhook(
    hub_mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    hub_verify_token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    hub_challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
) -> Response:
    """Apretón de manos de Meta.

    Meta llama con `hub.mode=subscribe` y el token que configuraste en el
    panel. Si coincide con `META_VERIFY_TOKEN`, hay que devolver el
    `hub.challenge` **en texto plano y sin comillas**: si se envuelve en JSON,
    Meta no lo reconoce y la verificación falla.
    """
    settings = get_settings()
    expected = settings.meta_verify_token

    if not expected:
        logger.error("webhook_verify_token_not_configured")
        return PlainTextResponse("", status_code=status.HTTP_503_SERVICE_UNAVAILABLE)

    if hub_mode != "subscribe" or hub_verify_token != expected:
        logger.warning("webhook_verification_rejected", mode=hub_mode)
        # 403 sin detalle: no se confirma qué parte falló (CLAUDE.md §8).
        return PlainTextResponse("", status_code=status.HTTP_403_FORBIDDEN)

    logger.info("webhook_verified")
    return PlainTextResponse(hub_challenge or "")


async def _resolve_channel(phone_number_id: str) -> tuple[TenantId, uuid.UUID] | None:
    """Tenant y canal a los que pertenece el número que recibió el mensaje.

    Va por la conexión de administración porque las políticas de RLS filtran
    por `app.tenant_id` y aquí todavía no sabemos cuál es — es justo lo que se
    está averiguando. Es lo mismo que hace `resolve_tenant_by_slug`.

    Sin registro no se procesa nada: CLAUDE.md §1.6 exige que ninguna
    respuesta salga sin `tenant_id` resuelto desde el `phone_number_id`.
    """
    from sqlalchemy.ext.asyncio import create_async_engine  # noqa: PLC0415

    settings = get_settings()
    engine = create_async_engine(settings.migration_url)
    try:
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text(
                        "SELECT tenant_id, id FROM whatsapp_accounts"
                        " WHERE phone_number_id = :pid AND status <> 'disabled'"
                        " LIMIT 1"
                    ),
                    {"pid": phone_number_id},
                )
            ).first()
    finally:
        await engine.dispose()

    if row is None:
        return None
    return TenantId(row[0]), uuid.UUID(str(row[1]))


@router.post("/whatsapp")
async def receive_webhook(request: Request) -> Response:
    """Recibe los eventos de Meta."""
    settings = get_settings()
    app_secret = settings.meta_app_secret

    # El cuerpo se lee crudo: la firma se calcula sobre estos bytes exactos.
    # Parsear y reserializar cambiaría espacios y orden de claves.
    body = await request.body()

    if not app_secret:
        # Sin secreto no se puede distinguir a Meta de un impostor. Se apaga.
        logger.error("webhook_app_secret_not_configured")
        return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)

    signature = request.headers.get("X-Hub-Signature-256")
    if not is_valid_signature(body=body, header=signature, app_secret=app_secret):
        logger.warning("webhook_invalid_signature")
        return Response(status_code=status.HTTP_403_FORBIDDEN)

    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001 - cuerpo ilegible: se acusa y se descarta
        logger.warning("webhook_unparseable_body")
        return Response(status_code=status.HTTP_200_OK)

    messages = parse_webhook(payload)
    if not messages:
        # Acuses de entrega y otros eventos suscritos. No son un error.
        logger.info("webhook_no_messages", field=payload.get("object"))
        return Response(status_code=status.HTTP_200_OK)

    for message in messages:
        try:
            channel = await _resolve_channel(message.phone_number_id)
            if channel is None:
                logger.error(
                    "webhook_unknown_phone_number_id",
                    phone_number_id=message.phone_number_id,
                )
                continue
            tenant_id, channel_id = channel
            await store_inbound_message(
                tenant_id=tenant_id, channel_id=channel_id, message=message
            )
        except Exception:  # noqa: BLE001
            # Se registra con traza y se sigue con el resto: un mensaje malo no
            # puede tumbar la entrega entera ni provocar que Meta reintente.
            logger.exception("webhook_message_failed", wamid=message.wamid)

    return Response(status_code=status.HTTP_200_OK)
