"""Motor y sesiones de base de datos.

El backend se conecta SIEMPRE con el rol de aplicación (`epm_app`), que no
omite RLS. La conexión con privilegios de DDL existe solo para Alembic y el
seed, y vive en `Settings.migration_url`.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config.settings import Settings, get_settings
from src.domain.value_objects import TenantId

#: Nombre del ajuste de sesión que leen las políticas de RLS.
TENANT_SETTING = "app.tenant_id"


def build_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        echo=settings.database_echo,
        pool_size=settings.database_pool_size,
        pool_pre_ping=True,
    )


@lru_cache
def get_engine() -> AsyncEngine:
    return build_engine(get_settings())


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False, autoflush=False)


@asynccontextmanager
async def tenant_session(tenant_id: TenantId) -> AsyncIterator[AsyncSession]:
    """Sesión con el tenant fijado para toda la transacción.

    Se usa `set_config(..., is_local => true)`, equivalente a `SET LOCAL`: el
    ajuste vive solo hasta el final de la transacción. Con `SET` a secas
    quedaría pegado a la conexión y, al devolverla al pool, la siguiente
    petición heredaría el tenant de la anterior — una fuga de datos entre
    clientes difícil de detectar.

    Como el ajuste es transaccional, la asignación y las consultas tienen que
    ir en la MISMA transacción; por eso se abre aquí explícitamente.
    """
    from sqlalchemy import text  # noqa: PLC0415  (import local: evita ciclo)

    session_factory = get_sessionmaker()
    async with session_factory() as session, session.begin():
        await session.execute(
            text(f"SELECT set_config('{TENANT_SETTING}', :tenant_id, true)"),
            {"tenant_id": str(tenant_id)},
        )
        yield session


async def dispose_engine() -> None:
    """Cierra el pool. Lo llama el `lifespan` de FastAPI al apagar."""
    await get_engine().dispose()
