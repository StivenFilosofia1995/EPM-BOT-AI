"""Publicación por lote de actividades en borrador.

El bot solo lee actividades `published` (ADR 005): mientras la parrilla siga
en `draft`, responde «no tengo cargada la programación», que es el
comportamiento correcto pero deja al bot sin nada que decir.

La pantalla de revisión del panel es el destino final de esto. Este comando
existe para el caso en que hace falta publicar **ya**, y mantiene lo esencial
de la revisión humana: **no publica nada sin `--confirm`**. Sin esa bandera
solo informa qué se publicaría, cuántas actividades traen advertencias y de
qué tipo — es decir, obliga a mirar antes de decidir, que es lo que el ADR
pide.
"""

from dataclasses import dataclass, field
from typing import Any, cast

from sqlalchemy import CursorResult, text

from src.domain.entities import PublicationStatus
from src.infrastructure.database.session import resolve_tenant_by_slug, tenant_session


@dataclass(frozen=True, slots=True)
class PublishResult:
    """Qué se publicó (o qué se publicaría, en simulación)."""

    tenant_slug: str
    venue_slug: str | None
    month: str | None
    candidates: int
    with_warnings: int
    published: int
    confirmed: bool
    warning_kinds: dict[str, int] = field(default_factory=dict)

    def render(self) -> str:
        scope = self.venue_slug or "todos los espacios"
        if self.month:
            scope += f" · {self.month}"
        lines = [f"{self.tenant_slug} -> {scope}"]

        if self.candidates == 0:
            lines.append("  No hay actividades en borrador que coincidan.")
            return "\n".join(lines)

        lines.append(
            f"  {self.candidates} en borrador · {self.with_warnings} con advertencia"
        )
        for kind, count in sorted(self.warning_kinds.items()):
            lines.append(f"    - {kind}: {count}")

        if self.confirmed:
            lines.append(f"  ✅ {self.published} publicadas.")
        else:
            lines.append(
                "  SIMULACIÓN: no se publicó nada. Revisá las advertencias de arriba "
                "y volvé a ejecutar con --confirm para publicar."
            )
        return "\n".join(lines)


async def publish_activities(
    *,
    tenant_slug: str,
    venue_slug: str | None = None,
    month: str | None = None,
    confirm: bool = False,
) -> PublishResult:
    """Pasa de `draft` a `published` las actividades que coincidan.

    `month` es `AAAA-MM` y se resuelve contra la hora de Bogotá, no UTC:
    publicar «julio» debe abarcar lo que el equipo ve como julio.

    Nunca toca actividades borradas ni las que ya están publicadas, así que
    ejecutarlo dos veces es inofensivo.
    """
    tenant_id = await resolve_tenant_by_slug(tenant_slug)
    if tenant_id is None:
        raise ValueError(f"El tenant '{tenant_slug}' no existe. ¿Falta cargar el seed?")

    conditions = [
        "a.tenant_id = :tenant_id",
        "a.status = :draft",
        "a.deleted_at IS NULL",
    ]
    params: dict[str, object] = {
        "tenant_id": str(tenant_id),
        "draft": PublicationStatus.DRAFT.value,
        "published": PublicationStatus.PUBLISHED.value,
    }

    if venue_slug:
        conditions.append(
            "a.venue_id = (SELECT id FROM venues WHERE slug = :venue_slug"
            " AND tenant_id = :tenant_id)"
        )
        params["venue_slug"] = venue_slug
    if month:
        year, month_number = _parse_month(month)
        conditions.append(
            "date_trunc('month', a.starts_at AT TIME ZONE 'America/Bogota')"
            " = make_date(:year, :month_number, 1)"
        )
        params["year"] = year
        params["month_number"] = month_number

    where = " AND ".join(conditions)

    async with tenant_session(tenant_id) as session:
        rows = await session.execute(
            text(f"SELECT a.warnings FROM activities a WHERE {where}"),  # noqa: S608
            params,
        )
        warning_kinds: dict[str, int] = {}
        candidates = 0
        with_warnings = 0
        for row in rows:
            candidates += 1
            warnings = list(row[0]) if row[0] else []
            if warnings:
                with_warnings += 1
            for warning in warnings:
                warning_kinds[warning] = warning_kinds.get(warning, 0) + 1

        published = 0
        if confirm and candidates:
            # `execute` de un UPDATE devuelve un CursorResult, que es quien
            # tiene `rowcount`; el tipo declarado de `execute` es el genérico.
            result = cast(
                "CursorResult[Any]",
                await session.execute(
                    text(  # noqa: S608
                        "UPDATE activities AS a SET status = :published,"
                        " published_at = now()"
                        f" WHERE {where}"
                    ),
                    params,
                ),
            )
            published = result.rowcount or 0

    return PublishResult(
        tenant_slug=tenant_slug,
        venue_slug=venue_slug,
        month=month,
        candidates=candidates,
        with_warnings=with_warnings,
        published=published,
        confirmed=confirm,
        warning_kinds=warning_kinds,
    )


def _parse_month(raw: str) -> tuple[int, int]:
    try:
        year, month = raw.split("-")
        parsed_year, parsed_month = int(year), int(month)
    except ValueError as exc:
        raise ValueError(f"--month debe ser AAAA-MM, no {raw!r}") from exc
    if not 1 <= parsed_month <= 12:
        raise ValueError(f"Mes fuera de rango: {parsed_month}")
    return parsed_year, parsed_month
