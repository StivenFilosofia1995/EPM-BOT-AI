"""Adaptador de Anthropic. Única implementación de `AIProviderPort` hoy
(ADR 004): cambiar de proveedor es cambiar `default_ai_provider`, no tocar
esta clase desde el resto del código."""

import time
from typing import Any

import anthropic
import structlog

from src.config.settings import Settings, get_settings
from src.domain.ports.ai_provider import (
    AIMessage,
    AIProviderPort,
    AIResponse,
    AIRole,
    AIUsage,
)
from src.domain.value_objects import TenantId

logger = structlog.get_logger()


def _to_anthropic_messages(messages: list[AIMessage]) -> list[dict[str, Any]]:
    # El system prompt va aparte en la API de Anthropic, nunca dentro de la
    # lista de mensajes: si alguien lo cuela aquí, se descarta en vez de
    # mandarlo con un rol que Anthropic rechaza.
    return [
        {"role": message.role.value, "content": message.content}
        for message in messages
        if message.role is not AIRole.SYSTEM
    ]


class AnthropicAdapter(AIProviderPort):
    """Genera texto con Claude a partir de contexto ya recuperado.

    No decide qué contexto usar ni valida la respuesta: eso es del caso de
    uso que orquesta la conversación. Esta clase solo habla con la API.
    """

    def __init__(self, settings: Settings) -> None:
        if not settings.anthropic_api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY no configurada: no se puede construir AnthropicAdapter."
            )
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = settings.anthropic_model

    async def complete(
        self,
        tenant_id: TenantId,
        messages: list[AIMessage],
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 1024,
    ) -> AIResponse:
        start = time.perf_counter()
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system or anthropic.NOT_GIVEN,  # type: ignore[arg-type]
            messages=_to_anthropic_messages(messages),  # type: ignore[arg-type]
            tools=tools or anthropic.NOT_GIVEN,  # type: ignore[arg-type]
        )
        latency_ms = round((time.perf_counter() - start) * 1000)

        text = "".join(block.text for block in response.content if block.type == "text")
        tool_calls = [
            {"id": block.id, "name": block.name, "input": block.input}
            for block in response.content
            if block.type == "tool_use"
        ]

        logger.info(
            "anthropic_completion",
            tenant_id=str(tenant_id),
            model=self._model,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            latency_ms=latency_ms,
        )

        return AIResponse(
            text=text,
            usage=AIUsage(
                tokens_in=response.usage.input_tokens,
                tokens_out=response.usage.output_tokens,
                latency_ms=latency_ms,
                model=self._model,
                provider="anthropic",
            ),
            stop_reason=response.stop_reason,
            tool_calls=tool_calls,
            raw=response.model_dump(mode="json"),
        )

    async def complete_with_vision(
        self,
        tenant_id: TenantId,
        messages: list[AIMessage],
        images: list[bytes],
        *,
        system: str | None = None,
        max_tokens: int = 4096,
    ) -> AIResponse:
        import base64  # noqa: PLC0415

        image_blocks: list[dict[str, Any]] = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": base64.b64encode(image).decode("ascii"),
                },
            }
            for image in images
        ]
        text_messages = _to_anthropic_messages(messages)
        if text_messages and image_blocks:
            last = text_messages[-1]
            last["content"] = [*image_blocks, {"type": "text", "text": last["content"]}]

        start = time.perf_counter()
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system or anthropic.NOT_GIVEN,  # type: ignore[arg-type]
            messages=text_messages,  # type: ignore[arg-type]
        )
        latency_ms = round((time.perf_counter() - start) * 1000)
        text = "".join(block.text for block in response.content if block.type == "text")

        return AIResponse(
            text=text,
            usage=AIUsage(
                tokens_in=response.usage.input_tokens,
                tokens_out=response.usage.output_tokens,
                latency_ms=latency_ms,
                model=self._model,
                provider="anthropic",
            ),
            stop_reason=response.stop_reason,
            raw=response.model_dump(mode="json"),
        )


_adapter: AnthropicAdapter | None = None


def get_ai_provider() -> AIProviderPort:
    """Instancia única del proveedor de IA configurado (hoy, siempre Anthropic).

    No usa `lru_cache` porque construir el adaptador puede lanzar
    (`ANTHROPIC_API_KEY` ausente); cachear una excepción dejaría el proceso
    fallando para siempre en vez de en cada intento.
    """
    global _adapter  # noqa: PLW0603
    if _adapter is None:
        _adapter = AnthropicAdapter(get_settings())
    return _adapter
