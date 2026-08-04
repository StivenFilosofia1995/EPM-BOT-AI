"""Dependencias compartidas de la capa de presentación.

⚠️ **La guarda de administración de este módulo es TEMPORAL.**

Un token compartido no es autenticación: no identifica a nadie, no tiene roles
y no permite saber quién hizo qué. Existe solo para que el panel no quede
abierto en internet entre P2B y P5, y **se elimina cuando entre la
autenticación de Supabase** con usuarios, roles y sesiones reales.

Mientras esto siga aquí, `audit_logs` registrará acciones sin un usuario real
detrás.
"""

import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from src.application.tenancy import TenantContext
from src.config.settings import Settings, get_settings


async def require_admin_token(
    x_admin_token: Annotated[str | None, Header()] = None,
    settings: Annotated[Settings, Depends(get_settings)] = None,  # type: ignore[assignment]
) -> None:
    """Exige la cabecera `X-Admin-Token`.

    Si no hay token configurado, se rechaza todo: es preferible que el panel
    no funcione a que funcione sin ninguna protección. Un despliegue al que se
    le olvidó la variable no debe quedar abierto por omisión.
    """
    expected = settings.admin_api_token
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Las rutas de administración están deshabilitadas: falta "
                "ADMIN_API_TOKEN en la configuración del servidor."
            ),
        )

    # Comparación en tiempo constante: comparar con `==` filtra información
    # sobre el token por el tiempo de respuesta.
    if not x_admin_token or not secrets.compare_digest(x_admin_token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de administración ausente o inválido",
        )


async def get_tenant_context(
    settings: Annotated[Settings, Depends(get_settings)],
) -> TenantContext:
    """Tenant activo de la petición.

    Hoy sale de la configuración porque no hay sesión de usuario. En P5 se
    deducirá del usuario autenticado, y el resto del código no cambia: ya
    recibe un `TenantContext`.
    """
    from src.infrastructure.database.session import resolve_tenant_by_slug  # noqa: PLC0415

    tenant_id = await resolve_tenant_by_slug(settings.default_tenant_slug)
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                f"El tenant '{settings.default_tenant_slug}' no existe. "
                "¿Falta cargar el seed?"
            ),
        )
    return TenantContext(tenant_id=tenant_id, tenant_slug=settings.default_tenant_slug)


AdminGuard = Annotated[None, Depends(require_admin_token)]
CurrentTenant = Annotated[TenantContext, Depends(get_tenant_context)]
