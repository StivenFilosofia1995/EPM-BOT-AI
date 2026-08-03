"""Identificadores del dominio. Sin dependencias externas (CLAUDE.md §3.1)."""

import re
from dataclasses import dataclass
from uuid import UUID

# E.164: '+' seguido de un dígito 1-9 y hasta 14 dígitos más.
_E164 = re.compile(r"^\+[1-9]\d{1,14}$")

# Los wamid de Meta llegan como 'wamid.<base64url>'. Se valida el prefijo y que
# el resto no esté vacío; el contenido exacto es opaco y no se interpreta.
_WAMID = re.compile(r"^wamid\.[A-Za-z0-9_\-=]+$")


@dataclass(frozen=True, slots=True)
class TenantId:
    """Identificador de tenant. Envuelve un UUID para que no se confunda
    con cualquier otro identificador al pasarlo entre capas."""

    value: UUID

    @classmethod
    def from_string(cls, raw: str) -> "TenantId":
        try:
            return cls(UUID(raw))
        except ValueError as exc:
            raise ValueError(f"TenantId inválido: {raw!r}") from exc

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class WaId:
    """Número de WhatsApp del contacto, en formato E.164.

    Meta entrega el `wa_id` sin el '+' inicial; `parse` lo acepta en ambas
    formas y normaliza siempre a E.164 con '+'.
    """

    value: str

    def __post_init__(self) -> None:
        if not _E164.match(self.value):
            raise ValueError(
                f"WaId debe cumplir E.164 (+ seguido de 2 a 15 dígitos): {self.value!r}"
            )

    @classmethod
    def parse(cls, raw: str) -> "WaId":
        candidate = raw.strip()
        if not candidate.startswith("+"):
            candidate = f"+{candidate}"
        return cls(candidate)

    @property
    def masked(self) -> str:
        """Versión enmascarada para logs (CLAUDE.md §8: nunca PII en claro)."""
        digits = self.value[1:]
        if len(digits) <= 6:
            return "*" * len(digits)
        return f"{digits[:2]}{'*' * (len(digits) - 6)}{digits[-4:]}"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Wamid:
    """Identificador de mensaje de Meta. Es la clave de idempotencia:
    un mismo `wamid` no puede procesarse dos veces (CLAUDE.md §3.4)."""

    value: str

    def __post_init__(self) -> None:
        if not _WAMID.match(self.value):
            raise ValueError(f"Wamid inválido: {self.value!r}")

    def __str__(self) -> str:
        return self.value
