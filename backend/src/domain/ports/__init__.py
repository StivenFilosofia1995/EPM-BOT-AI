"""Puertos del dominio: interfaces abstractas que la infraestructura implementa.

La dirección de las dependencias apunta siempre hacia adentro: el dominio
define el contrato, la infraestructura lo cumple (CLAUDE.md §3.1, ADR 002).
"""

from src.domain.ports.ai_provider import (
    AIMessage,
    AIProviderPort,
    AIResponse,
    AIRole,
    AIUsage,
)
from src.domain.ports.ingestion import (
    DiscoveredSource,
    IngestionSourcePort,
    RawContent,
)
from src.domain.ports.knowledge import ActivityQuery, KnowledgeRetrieverPort
from src.domain.ports.messaging import MessagingPort, SendResult
from src.domain.ports.repositories import ConversationRepositoryPort

__all__ = [
    "AIMessage",
    "AIProviderPort",
    "AIResponse",
    "AIRole",
    "AIUsage",
    "ActivityQuery",
    "ConversationRepositoryPort",
    "DiscoveredSource",
    "IngestionSourcePort",
    "KnowledgeRetrieverPort",
    "MessagingPort",
    "RawContent",
    "SendResult",
]
