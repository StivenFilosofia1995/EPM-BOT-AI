"""Base declarativa y piezas compartidas por todos los modelos.

Convenciones:
- Claves primarias UUID generadas por la base (`gen_random_uuid()`, pgcrypto).
- Todas las marcas de tiempo son `timestamptz` y se guardan en UTC
  (CLAUDE.md §5); la presentación en `America/Bogota` es cosa del frontend.
- Toda tabla de negocio lleva `tenant_id` y `tenant_id` es la primera columna
  de todo índice compuesto (CLAUDE.md §1.2).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, MetaData, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

#: Nombres deterministas para índices y restricciones. Sin esto, Alembic genera
#: nombres distintos en cada entorno y los `downgrade` se vuelven frágiles.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

#: Tablas sujetas a RLS. La migración recorre esta lista para crear las
#: políticas, de modo que añadir una tabla con `tenant_id` y olvidarse de la
#: política sea imposible: el test de aislamiento lo detecta.
TENANT_SCOPED_TABLES: tuple[str, ...] = (
    "users",
    "whatsapp_accounts",
    "templates",
    "contacts",
    "conversations",
    "messages",
    "venues",
    "rooms",
    "venue_facts",
    "activities",
    "activity_embeddings",
    "sources",
    "ingestion_runs",
    "ai_traces",
    "audit_logs",
)

#: Dimensión de los embeddings (CLAUDE.md §4).
EMBEDDING_DIM = 1024


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    type_annotation_map = {  # noqa: RUF012
        dict[str, Any]: JSONB,
        uuid.UUID: PgUUID(as_uuid=True),
    }


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


def tenant_fk() -> Mapped[uuid.UUID]:
    """Clave de tenant. `ON DELETE CASCADE`: borrar un tenant se lleva todo lo
    suyo, que es el comportamiento que exige una petición de supresión."""
    return mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class TimestampMixin:
    """`created_at` / `updated_at` gestionados por la base, no por Python:
    así son correctos aunque una fila se toque desde una migración o a mano."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
