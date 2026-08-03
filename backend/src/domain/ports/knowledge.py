"""Puerto de recuperación de conocimiento.

La recuperación es híbrida: primero un filtro SQL duro por tenant, espacio,
rango de fechas y audiencia; después re-ranking semántico con pgvector sobre
los candidatos. Las fechas y los espacios son filtros duros — la semántica
solo reordena (CLAUDE.md §3.5, ADR 006).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date

from src.domain.entities import Activity, VenueFact
from src.domain.value_objects import Audience, TenantId


@dataclass(frozen=True, slots=True)
class ActivityQuery:
    """Criterios de búsqueda de programación. `tenant_id` es obligatorio."""

    tenant_id: TenantId
    venue_slugs: list[str] | None = None
    date_from: date | None = None
    date_to: date | None = None
    audience: Audience | None = None
    text: str | None = None
    limit: int = 5


class KnowledgeRetrieverPort(ABC):
    """Recupera actividades y hechos publicados.

    Solo devuelve contenido en estado `published` y no borrado: un draft nunca
    puede llegar a una respuesta del bot.
    """

    @abstractmethod
    async def find_activities(self, query: ActivityQuery) -> list[Activity]:
        """Filtro estructurado + re-ranking semántico, en ese orden."""

    @abstractmethod
    async def find_venue_facts(
        self,
        tenant_id: TenantId,
        venue_slug: str,
        *,
        keys: list[str] | None = None,
        on_day: date | None = None,
    ) -> list[VenueFact]:
        """Hechos vigentes de un espacio: horarios, tarifas, contacto."""

    @abstractmethod
    async def has_programming_for(
        self,
        tenant_id: TenantId,
        venue_slug: str,
        year: int,
        month: int,
    ) -> bool:
        """¿Hay parrilla cargada para ese mes?

        Permite distinguir «no hay actividades» de «aún no se ha publicado el
        mes», que son respuestas distintas de cara al usuario (CLAUDE.md §7).
        """
