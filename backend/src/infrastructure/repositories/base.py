"""Repositorio base con filtro de tenant obligatorio.

Hay dos barreras independientes contra la fuga entre tenants:

1. **Aplicación** — este repositorio inyecta `WHERE tenant_id = :tenant` en
   toda consulta y lanza excepción si el tenant falta.
2. **Base de datos** — las políticas de RLS, que aplican aunque la capa 1
   tenga un fallo.

La segunda es la que de verdad protege; la primera existe para que los errores
se detecten pronto y con un mensaje claro, en vez de manifestarse como una
consulta que silenciosamente no devuelve nada.
"""

from typing import Any, TypeVar

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.tenancy import TenantNotResolvedError
from src.domain.value_objects import TenantId
from src.infrastructure.database.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseTenantRepository:
    """Base de todo repositorio de datos de negocio."""

    def __init__(self, session: AsyncSession, tenant_id: TenantId) -> None:
        if tenant_id is None:  # pragma: no cover - defensivo
            raise TenantNotResolvedError(
                f"{type(self).__name__} no puede construirse sin tenant_id"
            )
        self._session = session
        self._tenant_id = tenant_id

    @property
    def tenant_id(self) -> TenantId:
        return self._tenant_id

    @property
    def session(self) -> AsyncSession:
        return self._session

    def _scoped(self, model: type[ModelT]) -> Select[tuple[ModelT]]:
        """`SELECT` ya filtrado por tenant.

        Todo repositorio concreto debe partir de aquí. Construir un `select()`
        a pelo se salta la barrera de aplicación — RLS seguiría protegiendo,
        pero el error aparecería como «no hay resultados» en vez de como un
        fallo explícito.
        """
        return select(model).where(self._tenant_column(model) == self._tenant_id.value)

    @staticmethod
    def _tenant_column(model: type[ModelT]) -> Any:
        column = getattr(model, "tenant_id", None)
        if column is None:
            raise TypeError(
                f"{model.__name__} no tiene columna `tenant_id`: no puede usarse "
                "con un repositorio de tenant. Toda tabla de negocio la lleva "
                "(CLAUDE.md §1.2)."
            )
        return column

    def _with_tenant(self, values: dict[str, Any]) -> dict[str, Any]:
        """Añade el tenant a un diccionario de inserción.

        Si viene un `tenant_id` distinto al del repositorio, es un intento de
        escribir en otro tenant: se corta aquí (RLS también lo rechazaría).
        """
        incoming = values.get("tenant_id")
        if incoming is not None and incoming != self._tenant_id.value:
            raise TenantNotResolvedError(
                "Intento de escribir con un tenant_id distinto al del contexto: "
                f"{incoming} != {self._tenant_id.value}"
            )
        return {**values, "tenant_id": self._tenant_id.value}
