"""Implementación de `KnowledgeRetrieverPort` sobre SQL directo.

**Simplificación deliberada de esta primera versión:** solo filtro
estructurado (tenant, espacio, fechas, audiencia, texto por `ILIKE`). El
re-ranking semántico con `pgvector` (ADR 006, CLAUDE.md §3.5) queda para
cuando exista el pipeline de embeddings de `activities` — hoy
`activity_embeddings` no se puebla todavía. Mientras tanto, el filtro SQL ya
garantiza que el bot nunca inventa: solo devuelve lo que está `published`.
"""

from datetime import date
from typing import Any

from sqlalchemy import Row, text

from src.domain.entities import Activity, PublicationStatus, VenueFact
from src.domain.ports.knowledge import ActivityQuery, KnowledgeRetrieverPort
from src.domain.value_objects import Audience, Confidence, Money, TenantId
from src.infrastructure.database.session import tenant_session


class SqlKnowledgeRetriever(KnowledgeRetrieverPort):
    """Lee `activities` y `venue_facts` ya publicados, filtrados por tenant."""

    async def find_activities(self, query: ActivityQuery) -> list[Activity]:
        conditions = [
            "a.tenant_id = :tenant_id",
            "a.status = :published",
            "a.deleted_at IS NULL",
        ]
        params: dict[str, object] = {
            "tenant_id": str(query.tenant_id),
            "published": PublicationStatus.PUBLISHED.value,
            "limit": query.limit,
        }

        if query.venue_slugs:
            conditions.append("v.slug = ANY(:venue_slugs)")
            params["venue_slugs"] = list(query.venue_slugs)
        if query.date_from:
            conditions.append("a.starts_at >= :date_from")
            params["date_from"] = query.date_from
        if query.date_to:
            conditions.append("a.starts_at < (:date_to::date + 1)")
            params["date_to"] = query.date_to
        if query.audience:
            conditions.append("a.audience = :audience")
            params["audience"] = query.audience.value
        if query.text:
            conditions.append("(a.title ILIKE :search OR a.description ILIKE :search)")
            params["search"] = f"%{query.text}%"

        where = " AND ".join(conditions)
        async with tenant_session(query.tenant_id) as session:
            rows = await session.execute(
                text(  # noqa: S608
                    "SELECT a.id, a.venue_id, a.title, a.description, a.starts_at,"
                    " a.ends_at, a.room_id, a.room_raw, a.recurrence, a.audience,"
                    " a.age_min, a.age_max, a.audience_raw, a.price_amount,"
                    " a.price_currency, a.requires_registration, a.registration_url,"
                    " a.activity_group_id, a.source_id, a.source_url, a.source_row,"
                    " a.evidence_snippet, a.extracted_at, a.confidence, a.warnings,"
                    " a.extra, a.published_at, a.deleted_at, a.status, a.created_at"
                    " FROM activities a"
                    " JOIN venues v ON v.id = a.venue_id"
                    f" WHERE {where}"
                    " ORDER BY a.starts_at"
                    " LIMIT :limit"
                ),
                params,
            )
            return [self._to_activity(row, query.tenant_id) for row in rows]

    async def find_venue_facts(
        self,
        tenant_id: TenantId,
        venue_slug: str,
        *,
        keys: list[str] | None = None,
        on_day: date | None = None,
    ) -> list[VenueFact]:
        conditions = ["f.tenant_id = :tenant_id", "v.slug = :venue_slug"]
        params: dict[str, object] = {"tenant_id": str(tenant_id), "venue_slug": venue_slug}

        if keys:
            conditions.append("f.key = ANY(:keys)")
            params["keys"] = list(keys)
        if on_day:
            conditions.append("(f.valid_from IS NULL OR f.valid_from <= :on_day)")
            conditions.append("(f.valid_to IS NULL OR f.valid_to >= :on_day)")
            params["on_day"] = on_day

        where = " AND ".join(conditions)
        async with tenant_session(tenant_id) as session:
            rows = await session.execute(
                text(  # noqa: S608
                    "SELECT f.id, f.venue_id, f.key, f.value, f.valid_from, f.valid_to,"
                    " f.source_id, f.source_url, f.verified_at, f.confidence, f.created_at"
                    " FROM venue_facts f"
                    " JOIN venues v ON v.id = f.venue_id"
                    f" WHERE {where}"
                    " ORDER BY f.key"
                ),
                params,
            )
            return [
                VenueFact(
                    id=row[0],
                    tenant_id=tenant_id,
                    venue_id=row[1],
                    key=row[2],
                    value=row[3],
                    valid_from=row[4],
                    valid_to=row[5],
                    source_id=row[6],
                    source_url=row[7],
                    verified_at=row[8],
                    confidence=Confidence(float(row[9])),
                    created_at=row[10],
                )
                for row in rows
            ]

    async def has_programming_for(
        self,
        tenant_id: TenantId,
        venue_slug: str,
        year: int,
        month: int,
    ) -> bool:
        async with tenant_session(tenant_id) as session:
            found = await session.scalar(
                text(
                    "SELECT 1 FROM activities a"
                    " JOIN venues v ON v.id = a.venue_id"
                    " WHERE a.tenant_id = :tenant_id AND v.slug = :venue_slug"
                    " AND a.status = :published AND a.deleted_at IS NULL"
                    " AND date_trunc('month', a.starts_at AT TIME ZONE 'America/Bogota')"
                    "     = make_date(:year, :month, 1)"
                    " LIMIT 1"
                ),
                {
                    "tenant_id": str(tenant_id),
                    "venue_slug": venue_slug,
                    "published": PublicationStatus.PUBLISHED.value,
                    "year": year,
                    "month": month,
                },
            )
            return found is not None

    def _to_activity(self, row: Row[Any], tenant_id: TenantId) -> Activity:
        price_amount = row[13]
        price = (
            Money(amount_cents=price_amount, currency=row[14])
            if price_amount is not None
            else None
        )
        return Activity(
            id=row[0],
            tenant_id=tenant_id,
            venue_id=row[1],
            title=row[2],
            description=row[3],
            starts_at=row[4],
            ends_at=row[5],
            room_id=row[6],
            room_raw=row[7],
            recurrence=row[8],
            audience=Audience(row[9]) if row[9] else None,
            age_min=row[10],
            age_max=row[11],
            audience_raw=row[12],
            price=price,
            requires_registration=row[15],
            registration_url=row[16],
            activity_group_id=row[17],
            source_id=row[18],
            source_url=row[19],
            source_row=row[20],
            evidence_snippet=row[21],
            extracted_at=row[22],
            confidence=Confidence(float(row[23])),
            warnings=list(row[24]) if row[24] else [],
            extra=dict(row[25]) if row[25] else {},
            published_at=row[26],
            deleted_at=row[27],
            status=PublicationStatus(row[28]),
            created_at=row[29],
        )


_retriever: SqlKnowledgeRetriever | None = None


def get_knowledge_retriever() -> KnowledgeRetrieverPort:
    global _retriever  # noqa: PLW0603
    if _retriever is None:
        _retriever = SqlKnowledgeRetriever()
    return _retriever
