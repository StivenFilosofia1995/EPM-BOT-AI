"""Parser de fechas en español (contrato §3).

El campo `Fecha(s)` es el más difícil del archivo: es texto libre, **no lleva
año** y admite listas, recurrencias y rangos que cruzan de mes.

El año y el mes de referencia salen del título de la fila 1 («Programación
infantil – Julio 2026»), que es la única fuente del año en todo el libro. Si no
se puede leer, se usa el mes del parámetro de carga y se marca la fila con
confianza reducida — nunca se adivina.
"""

import calendar
import re
from dataclasses import dataclass, field
from datetime import date

from src.infrastructure.ingestion.excel.headers import normalize

MONTHS: dict[str, int] = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

#: Nombre del día -> weekday() de Python (lunes = 0).
WEEKDAYS: dict[str, int] = {
    "lunes": 0,
    "martes": 1,
    "miercoles": 2,
    "jueves": 3,
    "viernes": 4,
    "sabado": 5,
    "domingo": 6,
}

_MONTH_NAMES = "|".join(MONTHS)
_DAY_NAMES = "|".join(WEEKDAYS)

#: «Todos los martes de julio» — recurrencia semanal.
_RECURRING = re.compile(rf"todos\s+los\s+({_DAY_NAMES})s?\s+de\s+({_MONTH_NAMES})")
#: «Del 23 de junio al 9 de julio» — rango, puede cruzar de mes.
_RANGE = re.compile(
    rf"del\s+(\d{{1,2}})\s+de\s+({_MONTH_NAMES})\s+al?\s+(\d{{1,2}})\s+de\s+({_MONTH_NAMES})"
)
#: «14, 21 y 28 de julio» — lista de días con un mes al final.
_LIST = re.compile(rf"^(?P<days>[\d\s,y]+)\s+de\s+(?P<month>{_MONTH_NAMES})\s*$")


class DateParseError(ValueError):
    """La celda de fechas no se pudo interpretar. Es error de FILA, no del
    archivo: se reporta y se sigue con las demás."""


@dataclass(frozen=True, slots=True)
class ParsedDates:
    dates: list[date]
    recurrence: str | None = None
    """Texto original cuando la celda expresaba una recurrencia, para poder
    mostrarla tal cual («Todos los martes»)."""
    out_of_month: list[date] = field(default_factory=list)
    """Fechas fuera del mes de la carga. Se importan igual (§3.3)."""


def parse_month_year(title: str | None) -> tuple[int, int] | None:
    """Extrae (año, mes) del título de la fila 1.

    Ejemplo: «Programación infantil – Julio 2026» -> (2026, 7).
    """
    if not title:
        return None
    normalized = normalize(title)
    month_match = re.search(rf"({_MONTH_NAMES})", normalized)
    year_match = re.search(r"(20\d{2})", normalized)
    if not month_match or not year_match:
        return None
    return int(year_match.group(1)), MONTHS[month_match.group(1)]


def parse_weekdays(raw: str | None) -> set[int]:
    """Días de la semana declarados en «Día(s)».

    Sirve para dos cosas: acotar la expansión de un rango (§3.2) y validar de
    forma cruzada que la fecha cae en el día que dice la fila (§2).
    """
    if not raw:
        return set()
    normalized = normalize(raw)
    return {index for name, index in WEEKDAYS.items() if name in normalized}


def _weekdays_of_month(year: int, month: int, weekday: int) -> list[date]:
    _, last_day = calendar.monthrange(year, month)
    return [
        date(year, month, day)
        for day in range(1, last_day + 1)
        if date(year, month, day).weekday() == weekday
    ]


def _safe_date(year: int, month: int, day: int) -> date:
    try:
        return date(year, month, day)
    except ValueError as exc:
        # 31 de febrero: error de fila, no del archivo (§3.4).
        raise DateParseError(f"Fecha imposible: {day}/{month}/{year}") from exc


def parse_dates(
    raw: str | None,
    *,
    year: int,
    month: int,
    weekdays_raw: str | None = None,
) -> ParsedDates:
    """Convierte la celda `Fecha(s)` en la lista de fechas que representa.

    `year` y `month` son los de referencia (del título de la hoja o del
    parámetro de carga) y solo se usan cuando el texto no dice el mes.
    """
    if raw is None or not str(raw).strip():
        raise DateParseError("La celda de fechas está vacía")

    original = str(raw).strip()
    normalized = normalize(original)

    # 1) Recurrencia: «Todos los martes de julio».
    if (match := _RECURRING.search(normalized)) is not None:
        weekday = WEEKDAYS[match.group(1)]
        target_month = MONTHS[match.group(2)]
        dates = _weekdays_of_month(year, target_month, weekday)
        if not dates:
            raise DateParseError(f"La recurrencia no produjo fechas: {original!r}")
        return ParsedDates(
            dates=dates,
            recurrence=original,
            out_of_month=[d for d in dates if d.month != month],
        )

    # 2) Rango: «Del 23 de junio al 9 de julio».
    if (match := _RANGE.search(normalized)) is not None:
        start = _safe_date(year, MONTHS[match.group(2)], int(match.group(1)))
        end = _safe_date(year, MONTHS[match.group(4)], int(match.group(3)))
        if end < start:
            raise DateParseError(f"Rango invertido: {original!r}")
        wanted = parse_weekdays(weekdays_raw)
        dates = []
        cursor = start
        while cursor <= end:
            # Sin «Día(s)» se expande a todos los días del rango; con él,
            # solo a los días de semana indicados (§3.2).
            if not wanted or cursor.weekday() in wanted:
                dates.append(cursor)
            cursor = date.fromordinal(cursor.toordinal() + 1)
        if not dates:
            raise DateParseError(
                f"El rango {original!r} no contiene ninguno de los días indicados "
                f"en Día(s): {weekdays_raw!r}"
            )
        return ParsedDates(
            dates=dates,
            recurrence=original,
            out_of_month=[d for d in dates if d.month != month],
        )

    # 3) Lista: «01 de julio», «07 y 14 de julio», «02, 09, 16 y 23 de julio».
    if (match := _LIST.match(normalized)) is not None:
        target_month = MONTHS[match.group("month")]
        days = [int(d) for d in re.findall(r"\d{1,2}", match.group("days"))]
        if not days:
            raise DateParseError(f"No se encontró ningún día en {original!r}")
        dates = [_safe_date(year, target_month, day) for day in days]
        return ParsedDates(
            dates=sorted(dates),
            out_of_month=[d for d in dates if d.month != month],
        )

    raise DateParseError(f"Formato de fecha no reconocido: {original!r}")
