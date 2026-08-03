"""Value objects de apoyo: dinero, rangos de fechas, audiencia y confianza."""

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class Audience(StrEnum):
    """Público objetivo de una actividad (contrato de Excel §6)."""

    INFANTIL = "infantil"
    JUVENIL = "juvenil"
    ADULTO = "adulto"
    FAMILIAR = "familiar"
    TODO_PUBLICO = "todo_publico"


@dataclass(frozen=True, slots=True)
class Money:
    """Importe monetario.

    Se guarda en la unidad mínima (centavos) como entero: usar float para
    dinero acumula errores de redondeo, y aquí se muestran tarifas al público.
    """

    amount_cents: int
    currency: str = "COP"

    def __post_init__(self) -> None:
        if self.amount_cents < 0:
            raise ValueError("Money no admite importes negativos")
        if len(self.currency) != 3 or not self.currency.isalpha():
            raise ValueError(f"Moneda debe ser un código ISO 4217 de 3 letras: {self.currency!r}")
        object.__setattr__(self, "currency", self.currency.upper())

    @classmethod
    def from_cop(cls, pesos: int) -> "Money":
        return cls(amount_cents=pesos * 100, currency="COP")

    @property
    def is_free(self) -> bool:
        return self.amount_cents == 0

    def format_es_co(self) -> str:
        """Formato de cara al usuario: '$8.000' (separador de miles con punto)."""
        if self.is_free:
            return "Gratis"
        pesos = self.amount_cents // 100
        return f"${pesos:,}".replace(",", ".")


@dataclass(frozen=True, slots=True)
class DateRange:
    """Rango de fechas cerrado por ambos extremos."""

    start: date
    end: date

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError(f"DateRange invertido: {self.start} > {self.end}")

    def contains(self, moment: date | datetime) -> bool:
        day = moment.date() if isinstance(moment, datetime) else moment
        return self.start <= day <= self.end

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


@dataclass(frozen=True, slots=True)
class Confidence:
    """Confianza de un dato extraído, de 0.0 a 1.0.

    Toda actividad y todo hecho de espacio llevan uno: es lo que permite al
    panel priorizar la revisión humana y al bot decidir si un dato es fiable.
    """

    value: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.value <= 1.0:
            raise ValueError(f"Confidence debe estar entre 0.0 y 1.0: {self.value}")

    @classmethod
    def certain(cls) -> "Confidence":
        """Dato introducido o confirmado por una persona."""
        return cls(1.0)

    def is_below(self, threshold: float) -> bool:
        return self.value < threshold
