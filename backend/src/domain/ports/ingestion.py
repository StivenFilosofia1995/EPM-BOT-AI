"""Puerto de fuentes de ingesta.

Obtiene contenido crudo de una fuente. No interpreta ni estructura: eso es
trabajo de las etapas posteriores del pipeline (P2A).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from src.domain.value_objects import TenantId


@dataclass(frozen=True, slots=True)
class RawContent:
    """Contenido crudo tal cual se obtuvo de la fuente.

    `content_hash` permite saltarse el reprocesado cuando nada cambió, y
    `retrieved_at` deja constancia de cuándo se leyó.
    """

    source_id: UUID
    payload: bytes
    content_type: str
    content_hash: str
    retrieved_at: datetime
    origin_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DiscoveredSource:
    """Fuente descubierta dinámicamente.

    Los slugs de Issuu no son deterministas: se descubren cada mes desde los
    enlaces «Ver toda la programación» de la página oficial (KB §1, H4).
    """

    url: str
    label: str
    venue_slug: str | None = None
    period: str | None = None


class IngestionSourcePort(ABC):
    """Obtiene contenido crudo de una fuente concreta."""

    @abstractmethod
    async def discover(self, tenant_id: TenantId) -> list[DiscoveredSource]:
        """Descubre qué documentos hay disponibles ahora mismo.

        Las fuentes estáticas (un Excel que ya subió el operador) devuelven
        lista vacía: no hay nada que descubrir.
        """

    @abstractmethod
    async def fetch(self, tenant_id: TenantId, source_id: UUID) -> RawContent:
        """Descarga el contenido. Las fuentes de red respetan robots.txt,
        timeout, backoff exponencial y User-Agent identificable."""

    @abstractmethod
    async def supports(self, content_type: str) -> bool:
        """¿Esta fuente sabe manejar ese tipo de contenido?"""
