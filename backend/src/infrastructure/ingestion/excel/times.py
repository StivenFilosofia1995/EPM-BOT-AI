"""Parser de horarios en español (contrato §4).

La trampa clásica está aquí: **`12:00 m.` es el mediodía (12:00), no la
medianoche.** En español de Colombia `m.` abrevia *meridiem*. Confundirlo con
`a.m.` desplazaría la actividad doce horas y el bot daría una hora falsa.

`12:00 a.m.` sí es medianoche, y `12:00 p.m.` es mediodía, como en inglés.
"""

import re
from dataclasses import dataclass
from datetime import time

from src.infrastructure.ingestion.excel.headers import normalize

#: Separadores entre hora de inicio y de fin (§4). El guion largo aparece al
#: pegar desde Word.
_SEPARATORS = re.compile(r"\s+(?:a|hasta|-|–|—)\s+")

#: '2:00 p.m.', '10:00 a. m.', '12:00 m.', '14:00'. El sufijo es opcional
#: porque algunas filas usan formato de 24 h.
_TIME = re.compile(
    r"(?P<hour>\d{1,2})"
    r"(?::(?P<minute>\d{2}))?"
    r"\s*"
    r"(?P<suffix>a\.?\s*m\.?|p\.?\s*m\.?|m\.?)?",
)


class TimeParseError(ValueError):
    """El horario no se pudo interpretar. Error de FILA, no del archivo."""


@dataclass(frozen=True, slots=True)
class ParsedTime:
    start: time
    end: time | None
    """`None` cuando la celda no dice hora de fin. **Prohibido asumir una
    duración por defecto** (§4)."""


def _classify(suffix: str | None) -> str | None:
    """Normaliza el sufijo a 'am', 'pm', 'm' o None."""
    if not suffix:
        return None
    compact = suffix.replace(".", "").replace(" ", "")
    if compact == "am":
        return "am"
    if compact == "pm":
        return "pm"
    if compact == "m":
        return "m"
    return None


def _to_time(hour: int, minute: int, marker: str | None) -> time:
    if not 0 <= minute <= 59:
        raise TimeParseError(f"Minuto fuera de rango: {minute}")

    if marker == "m":
        # 'm.' = meridiem = mediodía. Solo tiene sentido con la hora 12.
        if hour != 12:
            raise TimeParseError(
                f"'{hour}:{minute:02d} m.' no es válido: 'm.' indica mediodía "
                "y solo acompaña a las 12"
            )
        return time(12, minute)

    if marker == "am":
        if not 1 <= hour <= 12:
            raise TimeParseError(f"Hora fuera de rango para a.m.: {hour}")
        # 12 a.m. es medianoche.
        return time(0 if hour == 12 else hour, minute)

    if marker == "pm":
        if not 1 <= hour <= 12:
            raise TimeParseError(f"Hora fuera de rango para p.m.: {hour}")
        # 12 p.m. es mediodía.
        return time(12 if hour == 12 else hour + 12, minute)

    # Sin sufijo: se interpreta como formato de 24 h.
    if not 0 <= hour <= 23:
        raise TimeParseError(f"Hora fuera de rango: {hour}")
    return time(hour, minute)


def _parse_single(fragment: str) -> time:
    match = _TIME.search(fragment)
    if match is None:
        raise TimeParseError(f"No se reconoce una hora en {fragment!r}")
    return _to_time(
        hour=int(match.group("hour")),
        minute=int(match.group("minute") or 0),
        marker=_classify(match.group("suffix")),
    )


def parse_time_range(raw: str | None) -> ParsedTime:
    """Interpreta la celda `Horario`.

    Ejemplos reales del archivo: '2:00 p.m. a 4:00 p.m.',
    '10:00 a.m. a 12:00 m.', '1:30 p.m. a 3:30 p.m.'.
    """
    if raw is None or not str(raw).strip():
        raise TimeParseError("La celda de horario está vacía")

    original = str(raw).strip()
    # `normalize` quita tildes, colapsa espacios y —clave aquí— convierte el
    # espacio duro que aparece en 'p. m.' al copiar desde Word.
    normalized = normalize(original)

    parts = [p for p in _SEPARATORS.split(normalized) if p.strip()]
    if not parts:
        raise TimeParseError(f"Horario vacío tras normalizar: {original!r}")

    start = _parse_single(parts[0])
    if len(parts) == 1:
        return ParsedTime(start=start, end=None)

    end = _parse_single(parts[1])
    if end < start:
        raise TimeParseError(
            f"La hora de fin ({end}) es anterior a la de inicio ({start}) en {original!r}"
        )
    return ParsedTime(start=start, end=end)
