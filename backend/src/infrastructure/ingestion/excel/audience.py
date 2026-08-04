"""Parser del público objetivo (contrato §6).

De una celda como «Niñas y niños de 4 a 7 años» salen tres datos: el enum de
audiencia, el rango de edad y el texto literal.

`audience_raw` se conserva **siempre**: es lo que el bot muestra al usuario.
Decirle «de 4 a 7 años» es más útil y más fiel que decirle «infantil».

Regla dura: **nunca se inventa un rango de edad.** Si la celda no lo dice, los
campos van a `None`.
"""

import re
from dataclasses import dataclass

from src.domain.value_objects import Audience
from src.infrastructure.ingestion.excel.headers import normalize

#: «de 4 a 7 años»
_RANGE = re.compile(r"de\s+(\d{1,2})\s+a\s+(\d{1,2})\s+anos?")
#: «de 9 años en adelante» -> sin límite superior
_FROM = re.compile(r"de\s+(\d{1,2})\s+anos?\s+en\s+adelante")
#: «mayores de 18 años»
_OLDER = re.compile(r"mayores\s+de\s+(\d{1,2})\s+anos?")
#: «menores de 12 años»
_YOUNGER = re.compile(r"menores\s+de\s+(\d{1,2})\s+anos?")

#: Pistas textuales -> audiencia. El orden importa: se evalúa de más
#: específico a más general.
_HINTS: tuple[tuple[tuple[str, ...], Audience], ...] = (
    (("familia", "todo publico", "todos los publicos"), Audience.FAMILIAR),
    (("nina", "nino", "infantil", "primera infancia"), Audience.INFANTIL),
    (("joven", "jovenes", "juvenil", "adolescente"), Audience.JUVENIL),
    (("adulto", "adultos", "adulto mayor"), Audience.ADULTO),
)

#: Umbrales de edad para deducir la audiencia cuando el texto no la nombra.
_CHILD_MAX = 12
_YOUTH_MAX = 26


@dataclass(frozen=True, slots=True)
class ParsedAudience:
    audience: Audience | None
    age_min: int | None
    age_max: int | None
    audience_raw: str | None
    from_sheet_name: bool = False
    """True si la audiencia se dedujo del nombre de la hoja porque la celda
    venía vacía. Implica confianza reducida (§6)."""


def _audience_from_text(normalized: str) -> Audience | None:
    for keywords, audience in _HINTS:
        if any(keyword in normalized for keyword in keywords):
            return audience
    return None


def _audience_from_ages(age_min: int | None, age_max: int | None) -> Audience | None:
    """Deduce la audiencia del rango cuando el texto no la nombra.

    Solo se usa como último recurso: el texto explícito siempre manda.
    """
    if age_max is not None and age_max <= _CHILD_MAX:
        return Audience.INFANTIL
    if age_min is not None and age_min >= _YOUTH_MAX:
        return Audience.ADULTO
    if age_min is not None and age_min <= _CHILD_MAX and age_max is None:
        return None  # «de 9 años en adelante» abarca demasiado para etiquetarlo
    if age_min is not None and age_min < _YOUTH_MAX:
        return Audience.JUVENIL
    return None


def parse_audience(raw: str | None, *, sheet_name: str | None = None) -> ParsedAudience:
    """Interpreta la celda `Público`.

    Si viene vacía se usa el nombre de la hoja como pista y se marca, para que
    el revisor sepa que ese dato no salió de la fila (§6).
    """
    if raw is None or not str(raw).strip():
        if sheet_name:
            deduced = _audience_from_text(normalize(sheet_name))
            if deduced is not None:
                return ParsedAudience(
                    audience=deduced,
                    age_min=None,
                    age_max=None,
                    audience_raw=None,
                    from_sheet_name=True,
                )
        return ParsedAudience(audience=None, age_min=None, age_max=None, audience_raw=None)

    original = str(raw).strip()
    normalized = normalize(original)

    age_min: int | None = None
    age_max: int | None = None

    if (range_match := _RANGE.search(normalized)) is not None:
        age_min, age_max = int(range_match.group(1)), int(range_match.group(2))
        if age_max < age_min:
            age_min, age_max = age_max, age_min
    # «de 9 años en adelante» y «mayores de 18 años» significan lo mismo para
    # nosotros: hay mínimo y no hay máximo.
    elif (lower_bound := _FROM.search(normalized) or _OLDER.search(normalized)) is not None:
        age_min = int(lower_bound.group(1))
    elif (upper_bound := _YOUNGER.search(normalized)) is not None:
        age_max = int(upper_bound.group(1))

    audience = _audience_from_text(normalized) or _audience_from_ages(age_min, age_max)

    return ParsedAudience(
        audience=audience,
        age_min=age_min,
        age_max=age_max,
        audience_raw=original,
    )
