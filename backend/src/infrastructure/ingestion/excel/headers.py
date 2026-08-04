"""Detección de encabezados y mapeo a campos canónicos.

Dos reglas del contrato que gobiernan este módulo:

- **La fila de encabezados no siempre es la 2.** Se escanean las 10 primeras
  y se elige la que traiga al menos 6 encabezados canónicos (§1).
- **La hoja se reconoce por sus encabezados, nunca por su nombre.** El nombre
  solo es una pista para el público (§1).

Ambas existen porque el archivo lo produce un equipo humano cada mes: una fila
en blanco de más o una hoja renombrada no pueden romper la importación.
"""

import unicodedata
from dataclasses import dataclass, field
from typing import Any

#: Filas a escanear buscando los encabezados (§1).
HEADER_SCAN_ROWS = 10

#: Mínimo de encabezados canónicos para aceptar una fila como cabecera (§1).
MIN_CANONICAL_HEADERS = 6

#: Encabezado normalizado -> campo canónico. Incluye los sinónimos del §2.
CANONICAL_HEADERS: dict[str, str] = {
    # Título
    "titulo del curso": "title",
    "titulo": "title",
    "actividad": "title",
    "nombre": "title",
    # Descripción
    "descripcion": "description",
    # Días de la semana (validación cruzada, §2)
    "dia(s)": "weekdays_raw",
    "dias": "weekdays_raw",
    "dia": "weekdays_raw",
    # Fechas
    "fecha(s)": "dates_raw",
    "fechas": "dates_raw",
    "fecha": "dates_raw",
    # Horario
    "horario": "time_raw",
    "hora": "time_raw",
    # Lugar
    "lugar": "room_raw",
    "espacio": "room_raw",
    "sala": "room_raw",
    # Público
    "publico": "audience_raw",
    "publico objetivo": "audience_raw",
    "dirigido a": "audience_raw",
    # Inscripción
    "inscripcion": "registration_raw",
    # Enlace
    "enlace de inscripcion": "registration_url",
    "enlace": "registration_url",
    "link de inscripcion": "registration_url",
}

#: Campos sin los que una fila no puede interpretarse (§2).
REQUIRED_FIELDS = ("title", "dates_raw", "time_raw")


def normalize(text: Any) -> str:
    """Minúsculas, sin tildes, sin espacios extremos y con los internos
    colapsados (§1).

    Se usa tanto para encabezados como para nombres de sala, así que el
    comportamiento tiene que ser idéntico en ambos.
    """
    if text is None:
        return ""
    raw = str(text).strip().lower()
    # NFD separa la tilde de la letra; se descartan las marcas diacríticas.
    decomposed = unicodedata.normalize("NFD", raw)
    without_accents = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    # El espacio duro (\xa0) es frecuente al copiar de Word y no lo pilla
    # `split()` en todas las versiones: se sustituye antes.
    return " ".join(without_accents.replace("\xa0", " ").split())


@dataclass(frozen=True, slots=True)
class HeaderMap:
    """Correspondencia entre columnas del archivo y campos canónicos."""

    row_number: int
    """Fila 1-based donde están los encabezados."""
    columns: dict[str, int]
    """campo canónico -> índice de columna (0-based)."""
    unknown: dict[str, int] = field(default_factory=dict)
    """encabezado original -> índice, para las columnas no reconocidas.
    Se conservan en `extra`, no se descartan (§2)."""

    def value(self, row: tuple[Any, ...], field_name: str) -> Any:
        index = self.columns.get(field_name)
        if index is None or index >= len(row):
            return None
        return row[index]

    def extras(self, row: tuple[Any, ...]) -> dict[str, Any]:
        return {
            header: row[index]
            for header, index in self.unknown.items()
            if index < len(row) and row[index] is not None
        }

    @property
    def is_usable(self) -> bool:
        return all(f in self.columns for f in REQUIRED_FIELDS)


def _score(cells: tuple[Any, ...]) -> int:
    return sum(1 for cell in cells if normalize(cell) in CANONICAL_HEADERS)


def find_header_row(rows: list[tuple[Any, ...]]) -> HeaderMap | None:
    """Busca la fila de encabezados entre las primeras `HEADER_SCAN_ROWS`.

    Devuelve `None` si ninguna llega al mínimo canónico: la hoja no es de
    programación y se ignora con aviso, no con error fatal (§1).
    """
    best: HeaderMap | None = None
    best_score = 0

    for index, cells in enumerate(rows[:HEADER_SCAN_ROWS]):
        score = _score(cells)
        if score < MIN_CANONICAL_HEADERS or score <= best_score:
            continue

        columns: dict[str, int] = {}
        unknown: dict[str, int] = {}
        for position, cell in enumerate(cells):
            normalized = normalize(cell)
            if not normalized:
                continue
            canonical = CANONICAL_HEADERS.get(normalized)
            if canonical is None:
                unknown[str(cell).strip()] = position
            elif canonical not in columns:
                # Ante encabezados duplicados gana el primero, que es el que
                # el operador ve más a la izquierda.
                columns[canonical] = position

        best = HeaderMap(row_number=index + 1, columns=columns, unknown=unknown)
        best_score = score

    return best
