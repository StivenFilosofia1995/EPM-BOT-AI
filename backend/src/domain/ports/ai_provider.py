"""Puerto de proveedor de IA.

Ninguna capa fuera de `infrastructure/ai/` puede conocer el proveedor concreto:
cambiar de Anthropic a OpenAI o Gemini debe ser cambiar una variable de entorno
(CLAUDE.md §2, ADR 004).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from src.domain.value_objects import TenantId


class AIRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class AIMessage:
    role: AIRole
    content: str


@dataclass(frozen=True, slots=True)
class AIUsage:
    """Consumo de una llamada, para alimentar `ai_traces`."""

    tokens_in: int
    tokens_out: int
    latency_ms: int
    model: str
    provider: str
    cost_estimate_usd: float | None = None


@dataclass(frozen=True, slots=True)
class AIResponse:
    text: str
    usage: AIUsage
    stop_reason: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


class AIProviderPort(ABC):
    """Genera texto a partir de un contexto ya recuperado.

    El modelo **solo redacta con lo que se le pasa**: si el contexto no trae el
    dato, la respuesta debe decirlo. Está prohibido completar con conocimiento
    paramétrico (CLAUDE.md §1.5).
    """

    @abstractmethod
    async def complete(
        self,
        tenant_id: TenantId,
        messages: list[AIMessage],
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 1024,
    ) -> AIResponse:
        """Completa una conversación. El `tenant_id` selecciona el proveedor,
        el modelo y las trazas correspondientes."""

    @abstractmethod
    async def complete_with_vision(
        self,
        tenant_id: TenantId,
        messages: list[AIMessage],
        images: list[bytes],
        *,
        system: str | None = None,
        max_tokens: int = 4096,
    ) -> AIResponse:
        """Completa con imágenes adjuntas.

        Lo usa el extractor de PDF de Issuu cuando la densidad de texto es
        insuficiente y hay que rasterizar las páginas (P2A).
        """
