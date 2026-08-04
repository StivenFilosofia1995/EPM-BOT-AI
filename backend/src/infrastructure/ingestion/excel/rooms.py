"""Resolución de salas contra el catálogo (contrato §5).

Dos reglas que parecen detalles y no lo son:

- **El número es significativo.** «Sala de Formación» y «Sala de Formación 3»
  son salas distintas. Tratarlas como la misma mandaría gente al sitio
  equivocado.
- **Una sala desconocida no se crea sola.** Se deja `room_raw` y se marca para
  que una persona la resuelva en el panel. Crear salas automáticamente llenaría
  el catálogo de erratas.
"""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from uuid import UUID

from src.application.ingestion.schemas import IngestionWarning
from src.infrastructure.ingestion.excel.headers import normalize

#: Umbral de coincidencia difusa (§5). Por encima se asigna con confianza
#: reducida; por debajo se deja sin resolver.
FUZZY_THRESHOLD = 0.85

#: Valores que significan «aquí no hay dato» y se convierten en NULL (§5).
SENTINELS = frozenset(
    {
        "no especificado en el documento",
        "no especificado",
        "no aplica",
        "n/a",
        "na",
        "-",
        "--",
        "por definir",
        "pendiente",
        "sin definir",
    }
)

_TRAILING_NUMBER = re.compile(r"\s+(\d+)$")


@dataclass(frozen=True, slots=True)
class RoomCatalog:
    """Salas conocidas de un espacio: nombre normalizado -> id."""

    by_name: dict[str, UUID]

    @classmethod
    def from_pairs(cls, pairs: list[tuple[str, UUID]]) -> "RoomCatalog":
        return cls(by_name={normalize(name): room_id for name, room_id in pairs})


@dataclass(frozen=True, slots=True)
class ResolvedRoom:
    room_id: UUID | None
    room_raw: str | None
    warnings: list[IngestionWarning]
    confidence_penalty: float = 0.0


def _room_number(normalized: str) -> str | None:
    match = _TRAILING_NUMBER.search(normalized)
    return match.group(1) if match else None


def _same_number(a: str, b: str) -> bool:
    """¿Ambos nombres se refieren a la misma sala numerada?

    Esto es lo que impide que la coincidencia difusa funda «sala de formacion»
    con «sala de formacion 3»: sus cadenas se parecen un 94 %, muy por encima
    del umbral, pero son sitios distintos.
    """
    return _room_number(a) == _room_number(b)


def resolve_room(raw: str | None, catalog: RoomCatalog) -> ResolvedRoom:
    if raw is None or not str(raw).strip():
        return ResolvedRoom(room_id=None, room_raw=None, warnings=[])

    original = str(raw).strip()
    normalized = normalize(original)

    if normalized in SENTINELS:
        # Centinela: no es el nombre de una sala, es la ausencia de dato.
        return ResolvedRoom(room_id=None, room_raw=None, warnings=[])

    # Coincidencia exacta tras normalizar. Resuelve «Taller Infantil» y
    # «Taller infantil» a la misma sala.
    if (room_id := catalog.by_name.get(normalized)) is not None:
        return ResolvedRoom(room_id=room_id, room_raw=original, warnings=[])

    best_id: UUID | None = None
    best_ratio = 0.0
    for candidate, room_id in catalog.by_name.items():
        if not _same_number(normalized, candidate):
            continue
        ratio = SequenceMatcher(None, normalized, candidate).ratio()
        if ratio > best_ratio:
            best_ratio, best_id = ratio, room_id

    if best_id is not None and best_ratio >= FUZZY_THRESHOLD:
        return ResolvedRoom(
            room_id=best_id,
            room_raw=original,
            warnings=[IngestionWarning.ROOM_FUZZY_MATCH],
            confidence_penalty=0.1,
        )

    # Desconocida: se conserva el texto y decide una persona (§5).
    return ResolvedRoom(
        room_id=None,
        room_raw=original,
        warnings=[IngestionWarning.ROOM_UNKNOWN],
        confidence_penalty=0.1,
    )
