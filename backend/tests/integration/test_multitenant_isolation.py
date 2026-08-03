"""Aislamiento multitenant verificado a nivel de RLS.

Este es el test más importante del proyecto: comprueba que la base de datos
—no la aplicación— impide que un tenant vea o escriba datos de otro.

Para que signifique algo, se conecta con el rol de aplicación (`epm_app`), que
NO omite RLS. Conectando con `postgres` estas pruebas pasarían siempre y no
demostrarían nada, porque ese rol tiene BYPASSRLS.

Requiere base de datos: se salta solo si no hay conexión configurada.
"""

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from src.config.settings import get_settings

pytestmark = pytest.mark.integration


def _requires_db() -> None:
    settings = get_settings()
    if "localhost" in settings.database_url or not settings.database_migration_url:
        pytest.skip("Sin base de datos real configurada (DATABASE_MIGRATION_URL)")


@pytest_asyncio.fixture
async def admin_conn() -> AsyncIterator[AsyncConnection]:
    """Conexión con BYPASSRLS: prepara el escenario y limpia al final.

    Se usa `connect()` y no `begin()` porque el fixture necesita hacer varios
    commits (crear los tenants, y luego borrarlos): con `begin()` la primera
    confirmación cerraría el contexto y las siguientes órdenes fallarían.
    """
    _requires_db()
    engine = create_async_engine(get_settings().migration_url)
    async with engine.connect() as conn:
        yield conn
    await engine.dispose()


@pytest_asyncio.fixture
async def app_conn() -> AsyncIterator[AsyncConnection]:
    """Conexión con el rol de aplicación: sujeta a RLS."""
    _requires_db()
    engine = create_async_engine(get_settings().database_url)
    async with engine.connect() as conn:
        yield conn
    await engine.dispose()


@pytest_asyncio.fixture
async def two_tenants(admin_conn: AsyncConnection) -> AsyncIterator[tuple[uuid.UUID, uuid.UUID]]:
    """Dos tenants con un espacio cada uno. Se borran al terminar."""
    suffix = uuid.uuid4().hex[:8]
    ids: list[uuid.UUID] = []
    for letra in ("a", "b"):
        tenant_id = await admin_conn.scalar(
            text("INSERT INTO tenants (name, slug) VALUES (:n, :s) RETURNING id"),
            {"n": f"Test {letra.upper()} {suffix}", "s": f"test-{letra}-{suffix}"},
        )
        assert tenant_id is not None
        ids.append(tenant_id)
        await admin_conn.execute(
            text(
                "INSERT INTO venues (tenant_id, slug, name, kind) "
                "VALUES (:t, :s, :n, 'otro')"
            ),
            {"t": tenant_id, "s": f"venue-{letra}-{suffix}", "n": f"Venue {letra.upper()}"},
        )
    await admin_conn.commit()

    yield ids[0], ids[1]

    await admin_conn.execute(
        text("DELETE FROM tenants WHERE id = ANY(:ids)"), {"ids": ids}
    )
    await admin_conn.commit()


async def _venues_seen_by(conn: AsyncConnection, tenant_id: uuid.UUID | None) -> list[str]:
    """Espacios visibles con un tenant dado en contexto.

    `set_config(..., true)` es un `SET LOCAL`: vive solo en esta transacción y
    se limpia al terminarla, así la conexión vuelve limpia al pool.
    """
    async with conn.begin():
        if tenant_id is not None:
            await conn.execute(
                text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
            )
        result = await conn.execute(text("SELECT slug FROM venues ORDER BY slug"))
        return [row[0] for row in result]


class TestRowLevelSecurity:
    async def test_app_role_does_not_bypass_rls(self, app_conn: AsyncConnection) -> None:
        """Si este test falla, todos los demás de esta clase son decorativos."""
        bypasses = await app_conn.scalar(
            text("SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user")
        )
        current_user = await app_conn.scalar(text("SELECT current_user"))
        assert bypasses is False, (
            f"El rol de runtime ({current_user}) omite RLS: el aislamiento en base "
            "de datos no está aplicándose."
        )

    async def test_tenant_sees_only_its_own_rows(
        self, app_conn: AsyncConnection, two_tenants: tuple[uuid.UUID, uuid.UUID]
    ) -> None:
        tenant_a, tenant_b = two_tenants

        seen_by_a = await _venues_seen_by(app_conn, tenant_a)
        seen_by_b = await _venues_seen_by(app_conn, tenant_b)

        assert len(seen_by_a) == 1
        assert len(seen_by_b) == 1
        assert seen_by_a != seen_by_b
        # Lo esencial: ninguno ve lo del otro.
        assert set(seen_by_a).isdisjoint(seen_by_b)

    async def test_without_tenant_context_sees_nothing(
        self, app_conn: AsyncConnection, two_tenants: tuple[uuid.UUID, uuid.UUID]
    ) -> None:
        """Sin `app.tenant_id` la política no encuentra nada.

        Es el fallo seguro: olvidarse de fijar el tenant devuelve cero filas,
        nunca las de todos.
        """
        assert await _venues_seen_by(app_conn, None) == []

    async def test_cannot_write_into_another_tenant(
        self, app_conn: AsyncConnection, two_tenants: tuple[uuid.UUID, uuid.UUID]
    ) -> None:
        """El `WITH CHECK` de la política bloquea la escritura cruzada."""
        tenant_a, tenant_b = two_tenants
        with pytest.raises(DBAPIError):
            async with app_conn.begin():
                await app_conn.execute(
                    text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_a)}
                )
                await app_conn.execute(
                    text(
                        "INSERT INTO venues (tenant_id, slug, name, kind) "
                        "VALUES (:t, 'intruso', 'Intruso', 'otro')"
                    ),
                    {"t": tenant_b},
                )

    async def test_tenant_context_does_not_leak_between_transactions(
        self, app_conn: AsyncConnection, two_tenants: tuple[uuid.UUID, uuid.UUID]
    ) -> None:
        """El ajuste es transaccional: no se queda pegado a la conexión.

        Si se filtrara, al reutilizar la conexión del pool la siguiente
        petición heredaría el tenant de la anterior.
        """
        tenant_a, _ = two_tenants
        assert len(await _venues_seen_by(app_conn, tenant_a)) == 1
        assert await _venues_seen_by(app_conn, None) == []

    async def test_admin_role_does_bypass_rls(
        self, admin_conn: AsyncConnection, two_tenants: tuple[uuid.UUID, uuid.UUID]
    ) -> None:
        """Contraprueba: el rol de migraciones sí lo ve todo.

        Confirma que las dos identidades se comportan de forma distinta y que
        el test anterior no pasa por accidente (por ejemplo, porque la tabla
        estuviera vacía).
        """
        result = await admin_conn.execute(text("SELECT count(*) FROM venues"))
        assert (result.scalar_one() or 0) >= 2


class TestRlsCoverage:
    async def test_every_tenant_table_has_rls_enabled_and_forced(
        self, admin_conn: AsyncConnection
    ) -> None:
        """Una tabla con `tenant_id` y sin política es una fuga.

        FORCE es imprescindible: sin él, el dueño de la tabla (`postgres`, que
        es quien migra) se salta la política aunque esté activada.
        """
        from src.infrastructure.database.models.base import (  # noqa: PLC0415
            TENANT_SCOPED_TABLES,
        )

        rows = await admin_conn.execute(
            text(
                "SELECT relname, relrowsecurity, relforcerowsecurity "
                "FROM pg_class WHERE relnamespace = 'public'::regnamespace AND relkind = 'r'"
            )
        )
        state = {r[0]: (r[1], r[2]) for r in rows}

        problems = []
        for table in (*TENANT_SCOPED_TABLES, "tenants"):
            enabled, forced = state.get(table, (False, False))
            if not enabled:
                problems.append(f"{table}: RLS desactivado")
            elif not forced:
                problems.append(f"{table}: RLS sin FORCE")
        assert not problems, problems

    async def test_every_tenant_table_has_an_isolation_policy(
        self, admin_conn: AsyncConnection
    ) -> None:
        from src.infrastructure.database.models.base import (  # noqa: PLC0415
            TENANT_SCOPED_TABLES,
        )

        rows = await admin_conn.execute(
            text("SELECT tablename FROM pg_policies WHERE policyname = 'tenant_isolation'")
        )
        with_policy = {r[0] for r in rows}
        missing = {*TENANT_SCOPED_TABLES, "tenants"} - with_policy
        assert not missing, f"Tablas sin política de aislamiento: {sorted(missing)}"
