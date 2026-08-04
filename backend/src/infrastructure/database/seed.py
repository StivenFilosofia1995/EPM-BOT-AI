"""Carga del seed de un tenant desde `data/seeds/<slug>/`.

Es idempotente: se puede ejecutar tantas veces como haga falta y converge al
contenido de los YAML. Un dato del seed que ya existe se actualiza, no se
duplica.

Usa la conexión de MIGRACIONES a propósito. El seed crea el tenant, y las
políticas de RLS impiden ver o insertar filas de un tenant que aún no está en
contexto — el huevo y la gallina. Es una tarea de administración, no de
runtime.
"""

import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from src.config.settings import get_settings

SEEDS_ROOT = Path(__file__).resolve().parents[4] / "data" / "seeds"


@dataclass(frozen=True, slots=True)
class SeedReport:
    tenant_slug: str
    tenant_created: bool
    venues_inserted: int
    venues_updated: int
    facts_inserted: int
    facts_updated: int
    rooms_inserted: int = 0
    rooms_updated: int = 0

    def render(self) -> str:
        estado = "creado" if self.tenant_created else "ya existía"
        return (
            f"Tenant '{self.tenant_slug}': {estado}\n"
            f"  espacios: {self.venues_inserted} nuevos, {self.venues_updated} actualizados\n"
            f"  salas:    {self.rooms_inserted} nuevas, {self.rooms_updated} actualizadas\n"
            f"  hechos:   {self.facts_inserted} nuevos, {self.facts_updated} actualizados"
        )


def _load_yaml(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"Falta el archivo de seed: {path}")
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _parse_verified_at(raw: str | date | None) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.astimezone(UTC)
    if isinstance(raw, date):
        return datetime(raw.year, raw.month, raw.day, tzinfo=UTC)
    return datetime.fromisoformat(str(raw)).replace(tzinfo=UTC)


async def _seed_tenant(conn: AsyncConnection, data: dict[str, Any]) -> tuple[str, bool]:
    existing = await conn.scalar(
        text("SELECT id FROM tenants WHERE slug = :slug"), {"slug": data["slug"]}
    )
    if existing is not None:
        await conn.execute(
            text(
                "UPDATE tenants SET name = :name, status = :status, settings = :settings "
                "WHERE id = :id"
            ),
            {
                "id": existing,
                "name": data["name"],
                "status": data.get("status", "active"),
                "settings": _jsonb(data.get("settings", {})),
            },
        )
        return str(existing), False

    tenant_id = await conn.scalar(
        text(
            "INSERT INTO tenants (name, slug, status, settings) "
            "VALUES (:name, :slug, :status, :settings) RETURNING id"
        ),
        {
            "name": data["name"],
            "slug": data["slug"],
            "status": data.get("status", "active"),
            "settings": _jsonb(data.get("settings", {})),
        },
    )
    return str(tenant_id), True


def _jsonb(value: Any) -> str:
    import json  # noqa: PLC0415

    return json.dumps(value, ensure_ascii=False, default=str)


async def _seed_venues(
    conn: AsyncConnection, tenant_id: str, venues: list[dict[str, Any]]
) -> tuple[int, int]:
    inserted = updated = 0
    for venue in venues:
        params = {
            "tenant_id": tenant_id,
            "slug": venue["slug"],
            "name": venue["name"],
            "kind": venue["kind"],
            "address": venue.get("address"),
            "neighborhood": venue.get("neighborhood"),
            "city": venue.get("city", "Medellín"),
            "phones": venue.get("phones", []),
            "emails": venue.get("emails", []),
            "metadata": _jsonb(venue.get("metadata", {})),
        }
        existing = await conn.scalar(
            text("SELECT id FROM venues WHERE tenant_id = :tenant_id AND slug = :slug"),
            {"tenant_id": tenant_id, "slug": venue["slug"]},
        )
        if existing is None:
            await conn.execute(
                text(
                    "INSERT INTO venues (tenant_id, slug, name, kind, address, neighborhood,"
                    " city, phones, emails, metadata) VALUES (:tenant_id, :slug, :name, :kind,"
                    " :address, :neighborhood, :city, :phones, :emails, :metadata)"
                ),
                params,
            )
            inserted += 1
        else:
            await conn.execute(
                text(
                    "UPDATE venues SET name = :name, kind = :kind, address = :address,"
                    " neighborhood = :neighborhood, city = :city, phones = :phones,"
                    " emails = :emails, metadata = :metadata"
                    " WHERE tenant_id = :tenant_id AND slug = :slug"
                ),
                params,
            )
            updated += 1
    return inserted, updated


async def _seed_rooms(
    conn: AsyncConnection, tenant_id: str, rooms_by_venue: dict[str, list[dict[str, Any]]]
) -> tuple[int, int]:
    """Catálogo de salas por espacio (contrato §5).

    Sin catálogo el importador de Excel no puede resolver el campo `Lugar` y
    deja todas las filas con la sala sin resolver.
    """
    inserted = updated = 0
    for venue_slug, rooms in rooms_by_venue.items():
        venue_id = await conn.scalar(
            text("SELECT id FROM venues WHERE tenant_id = :tenant_id AND slug = :slug"),
            {"tenant_id": tenant_id, "slug": venue_slug},
        )
        if venue_id is None:
            raise ValueError(f"rooms.yaml referencia el espacio '{venue_slug}', que no existe")

        for room in rooms:
            params = {
                "tenant_id": tenant_id,
                "venue_id": venue_id,
                "name": room["name"],
                "normalized_name": room["normalized_name"],
                "capacity": room.get("capacity"),
            }
            existing = await conn.scalar(
                text(
                    "SELECT id FROM rooms WHERE tenant_id = :tenant_id"
                    " AND venue_id = :venue_id AND normalized_name = :normalized_name"
                ),
                params,
            )
            if existing is None:
                await conn.execute(
                    text(
                        "INSERT INTO rooms (tenant_id, venue_id, name, normalized_name, capacity)"
                        " VALUES (:tenant_id, :venue_id, :name, :normalized_name, :capacity)"
                    ),
                    params,
                )
                inserted += 1
            else:
                await conn.execute(
                    text("UPDATE rooms SET name = :name, capacity = :capacity WHERE id = :id"),
                    {**params, "id": existing},
                )
                updated += 1
    return inserted, updated


async def _seed_facts(
    conn: AsyncConnection, tenant_id: str, facts: list[dict[str, Any]]
) -> tuple[int, int]:
    inserted = updated = 0
    for fact in facts:
        venue_id = await conn.scalar(
            text("SELECT id FROM venues WHERE tenant_id = :tenant_id AND slug = :slug"),
            {"tenant_id": tenant_id, "slug": fact["venue_slug"]},
        )
        if venue_id is None:
            raise ValueError(
                f"El hecho '{fact['key']}' referencia el espacio "
                f"'{fact['venue_slug']}', que no está en venues.yaml"
            )
        # Un dato sin fuente no entra a la base (KB, regla de oro).
        if not fact.get("source_url"):
            raise ValueError(f"El hecho '{fact['key']}' de '{fact['venue_slug']}' no tiene fuente")

        params = {
            "tenant_id": tenant_id,
            "venue_id": venue_id,
            "key": fact["key"],
            "value": fact["value"].strip(),
            "source_url": fact["source_url"],
            "verified_at": _parse_verified_at(fact.get("verified_at")),
            "confidence": float(fact.get("confidence", 1.0)),
        }
        existing = await conn.scalar(
            text(
                "SELECT id FROM venue_facts WHERE tenant_id = :tenant_id"
                " AND venue_id = :venue_id AND key = :key"
            ),
            {"tenant_id": tenant_id, "venue_id": venue_id, "key": fact["key"]},
        )
        if existing is None:
            await conn.execute(
                text(
                    "INSERT INTO venue_facts (tenant_id, venue_id, key, value, source_url,"
                    " verified_at, confidence) VALUES (:tenant_id, :venue_id, :key, :value,"
                    " :source_url, :verified_at, :confidence)"
                ),
                params,
            )
            inserted += 1
        else:
            await conn.execute(
                text(
                    "UPDATE venue_facts SET value = :value, source_url = :source_url,"
                    " verified_at = :verified_at, confidence = :confidence WHERE id = :id"
                ),
                {**params, "id": existing},
            )
            updated += 1
    return inserted, updated


async def load_seed(tenant_slug: str) -> SeedReport:
    seed_dir = SEEDS_ROOT / tenant_slug
    tenant_data = _load_yaml(seed_dir / "tenant.yaml")
    venues = _load_yaml(seed_dir / "venues.yaml") or []
    facts = _load_yaml(seed_dir / "venue_facts.yaml") or []
    rooms_path = seed_dir / "rooms.yaml"
    rooms = _load_yaml(rooms_path) if rooms_path.exists() else {}

    engine = create_async_engine(get_settings().migration_url)
    try:
        async with engine.begin() as conn:
            tenant_id, created = await _seed_tenant(conn, tenant_data)
            v_ins, v_upd = await _seed_venues(conn, tenant_id, venues)
            r_ins, r_upd = await _seed_rooms(conn, tenant_id, rooms or {})
            f_ins, f_upd = await _seed_facts(conn, tenant_id, facts)
    finally:
        await engine.dispose()

    return SeedReport(
        tenant_slug=tenant_slug,
        tenant_created=created,
        venues_inserted=v_ins,
        venues_updated=v_upd,
        rooms_inserted=r_ins,
        rooms_updated=r_upd,
        facts_inserted=f_ins,
        facts_updated=f_upd,
    )


def main() -> None:
    import sys  # noqa: PLC0415

    slug = sys.argv[1] if len(sys.argv) > 1 else "fundacion-epm"
    report = asyncio.run(load_seed(slug))
    print(report.render())  # noqa: T201


if __name__ == "__main__":
    main()
