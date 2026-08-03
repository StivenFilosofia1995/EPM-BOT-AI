"""Contexto de tenant.

Es la pieza que garantiza la regla más importante del sistema: ninguna
operación ocurre sin un tenant resuelto (CLAUDE.md §1.2 y §1.6). Si algo llega
hasta aquí sin tenant, es un fallo de programación y se detiene con una
excepción, no con un valor por defecto.
"""

from dataclasses import dataclass
from uuid import UUID

from src.domain.value_objects import TenantId


class TenantNotResolvedError(RuntimeError):
    """No se pudo determinar el tenant de la operación.

    En el webhook esto significa `phone_number_id` desconocido: se registra el
    intento y se descarta el evento, nunca se procesa (CLAUDE.md §3.4).
    """


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Tenant activo y, si aplica, el usuario que actúa."""

    tenant_id: TenantId
    tenant_slug: str | None = None
    user_id: UUID | None = None

    @classmethod
    def from_uuid(cls, raw: UUID | str, **kwargs: object) -> "TenantContext":
        tenant_id = TenantId(raw) if isinstance(raw, UUID) else TenantId.from_string(raw)
        return cls(tenant_id=tenant_id, **kwargs)  # type: ignore[arg-type]

    def require(self) -> TenantId:
        """Devuelve el tenant o falla. Punto único donde se comprueba."""
        if self.tenant_id is None:  # pragma: no cover - defensivo
            raise TenantNotResolvedError("La operación requiere un tenant resuelto")
        return self.tenant_id
