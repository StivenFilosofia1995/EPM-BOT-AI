"""Adaptador de `MessagingPort` contra la Graph API de WhatsApp Cloud.

Única implementación permitida: habla con la API oficial de Meta, nunca con
una librería no oficial (CLAUDE.md §1.1).
"""

from typing import Any

import httpx
import structlog

from src.config.settings import Settings, get_settings
from src.domain.ports.messaging import MessagingPort, SendResult
from src.domain.value_objects import TenantId, WaId, Wamid

logger = structlog.get_logger()


class MetaMessagingAdapter(MessagingPort):
    """Envía mensajes y plantillas vía Graph API, usando el número y el
    token configurados para el tenant (hoy, uno solo por Settings; con más
    de un tenant esto pasa a resolverse por tenant_id, no por variable
    global — ver CLAUDE.md §1.6)."""

    def __init__(self, settings: Settings) -> None:
        if not settings.meta_access_token or not settings.meta_phone_number_id:
            raise ValueError(
                "META_ACCESS_TOKEN y META_PHONE_NUMBER_ID son obligatorios para "
                "construir MetaMessagingAdapter."
            )
        self._token = settings.meta_access_token
        self._phone_number_id = settings.meta_phone_number_id
        self._base_url = (
            f"https://graph.facebook.com/{settings.meta_graph_api_version}"
            f"/{settings.meta_phone_number_id}"
        )

    async def _post(self, payload: dict[str, Any]) -> SendResult:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self._base_url}/messages",
                headers={"Authorization": f"Bearer {self._token}"},
                json=payload,
            )
        body = response.json()
        if response.status_code >= httpx.codes.BAD_REQUEST:
            error = body.get("error", {})
            logger.warning(
                "meta_send_failed",
                status_code=response.status_code,
                error_code=error.get("code"),
                error_message=error.get("message"),
            )
            return SendResult(
                wamid=None,
                accepted=False,
                error_code=str(error.get("code", response.status_code)),
                error_message=error.get("message"),
                raw=body,
            )

        wamid_raw = (body.get("messages") or [{}])[0].get("id")
        return SendResult(
            wamid=Wamid(wamid_raw) if wamid_raw else None,
            accepted=True,
            raw=body,
        )

    async def send_text(
        self,
        tenant_id: TenantId,
        to: WaId,
        body: str,
        *,
        preview_url: bool = False,
    ) -> SendResult:
        return await self._post(
            {
                "messaging_product": "whatsapp",
                "to": str(to),
                "type": "text",
                "text": {"body": body, "preview_url": preview_url},
            }
        )

    async def send_template(
        self,
        tenant_id: TenantId,
        to: WaId,
        template_name: str,
        language: str,
        *,
        parameters: dict[str, Any] | None = None,
    ) -> SendResult:
        components = (
            [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": value} for value in parameters.values()
                    ],
                }
            ]
            if parameters
            else []
        )
        return await self._post(
            {
                "messaging_product": "whatsapp",
                "to": str(to),
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": language},
                    "components": components,
                },
            }
        )

    async def send_interactive(
        self,
        tenant_id: TenantId,
        to: WaId,
        body: str,
        buttons: list[str],
        *,
        header: str | None = None,
        footer: str | None = None,
    ) -> SendResult:
        action = {
            "buttons": [
                {"type": "reply", "reply": {"id": f"btn_{i}", "title": label[:20]}}
                for i, label in enumerate(buttons)
            ]
        }
        interactive: dict[str, Any] = {
            "type": "button",
            "body": {"text": body},
            "action": action,
        }
        if header:
            interactive["header"] = {"type": "text", "text": header}
        if footer:
            interactive["footer"] = {"text": footer}
        return await self._post(
            {
                "messaging_product": "whatsapp",
                "to": str(to),
                "type": "interactive",
                "interactive": interactive,
            }
        )

    async def mark_as_read(self, tenant_id: TenantId, wamid: Wamid) -> bool:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self._base_url}/messages",
                headers={"Authorization": f"Bearer {self._token}"},
                json={
                    "messaging_product": "whatsapp",
                    "status": "read",
                    "message_id": str(wamid),
                },
            )
        return response.status_code < httpx.codes.BAD_REQUEST


_adapter: MetaMessagingAdapter | None = None


def get_messaging_port() -> MessagingPort:
    """Instancia única del adaptador de mensajería.

    Sin `lru_cache` por el mismo motivo que `get_ai_provider`: construirlo
    puede fallar si faltan credenciales, y no queremos cachear ese fallo.
    """
    global _adapter  # noqa: PLW0603
    if _adapter is None:
        _adapter = MetaMessagingAdapter(get_settings())
    return _adapter
