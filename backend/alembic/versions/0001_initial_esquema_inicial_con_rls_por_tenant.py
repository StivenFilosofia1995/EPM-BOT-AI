"""esquema inicial con RLS por tenant

Crea las 16 tablas, el rol de aplicación `epm_app` y las políticas de Row Level
Security que aíslan los tenants en la capa de datos (CLAUDE.md §8, ADR 003).

Sobre el rol de aplicación
--------------------------
En Supabase el usuario `postgres` tiene BYPASSRLS, y en PostgreSQL el dueño de
la tabla también omite RLS. Como las migraciones corren con `postgres`, las
tablas quedan a su nombre: si el backend se conectara con ese mismo usuario,
las políticas no se aplicarían nunca y el aislamiento sería solo de aplicación.

Por eso se crea `epm_app` (NOBYPASSRLS, no dueño de nada) y se activa además
FORCE ROW LEVEL SECURITY, que hace que las políticas apliquen incluso al dueño.

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-03
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from src.config.settings import get_settings
from src.infrastructure.database.models.base import EMBEDDING_DIM, TENANT_SCOPED_TABLES

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "epm_app"

#: Expresión del tenant activo. `NULLIF(..., '')` evita que una cadena vacía
#: reviente el cast a uuid, y el `true` de `current_setting` hace que devuelva
#: NULL en vez de error cuando la variable no está puesta. Resultado: sin
#: `app.tenant_id` no se ve ninguna fila.
CURRENT_TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def _app_role_password() -> str:
    # El .env lo lee `Settings`, no `os.environ`; se admite también la variable
    # de entorno directa para despliegues que inyecten secretos así.
    password = get_settings().app_db_password or os.environ.get("APP_DB_PASSWORD")
    if not password:
        raise RuntimeError(
            "Falta APP_DB_PASSWORD. Es la contraseña del rol de aplicación "
            f"`{APP_ROLE}`, que es quien se conecta en runtime sin omitir RLS. "
            "Defínela en el .env antes de migrar (ver docs/DATABASE.md)."
        )
    return password


def _ts_columns() -> list[sa.Column[sa.DateTime]]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    # --- Extensiones -------------------------------------------------------
    # pgcrypto da gen_random_uuid(); vector habilita el re-ranking semántico.
    # En Supabase viven en el esquema `extensions`, que ya está en search_path.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions")

    # --- identity ----------------------------------------------------------
    op.create_table(
        "tenants",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), server_default="active", nullable=False),
        sa.Column("settings", postgresql.JSONB(), server_default="{}", nullable=False),
        *_ts_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_tenants"),
        sa.UniqueConstraint("slug", name="uq_tenants_slug"),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=True),
        sa.Column("auth_user_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        *_ts_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_users_tenant_id_tenants", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("tenant_id", "email", name="uq_users_tenant_id_email"),
    )
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])
    op.create_index("ix_users_tenant_id_role", "users", ["tenant_id", "role"])

    # --- channels ----------------------------------------------------------
    op.create_table(
        "whatsapp_accounts",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("waba_id", sa.String(64), nullable=False),
        sa.Column("phone_number_id", sa.String(64), nullable=False),
        sa.Column("display_number", sa.String(32), nullable=False),
        sa.Column("verified_name", sa.String(200), nullable=True),
        sa.Column("token_ref", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        *_ts_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_whatsapp_accounts_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_whatsapp_accounts"),
        # Global a propósito: un phone_number_id solo puede pertenecer a un
        # tenant. Es lo que hace segura la resolución de tenant del webhook.
        sa.UniqueConstraint("phone_number_id", name="uq_whatsapp_accounts_phone_number_id"),
    )
    op.create_index("ix_whatsapp_accounts_tenant_id", "whatsapp_accounts", ["tenant_id"])
    op.create_index(
        "ix_whatsapp_accounts_tenant_id_status", "whatsapp_accounts", ["tenant_id", "status"]
    )

    op.create_table(
        "templates",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("language", sa.String(10), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("components", postgresql.JSONB(), nullable=True),
        *_ts_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_templates_tenant_id_tenants", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_templates"),
        sa.UniqueConstraint(
            "tenant_id", "name", "language", name="uq_templates_tenant_id_name_language"
        ),
    )
    op.create_index("ix_templates_tenant_id", "templates", ["tenant_id"])
    op.create_index("ix_templates_tenant_id_status", "templates", ["tenant_id", "status"])

    # --- conversations -----------------------------------------------------
    op.create_table(
        "contacts",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("wa_id", sa.String(20), nullable=False),
        sa.Column("profile_name", sa.String(200), nullable=True),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opt_out_at", sa.DateTime(timezone=True), nullable=True),
        *_ts_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_contacts_tenant_id_tenants", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_contacts"),
        sa.UniqueConstraint("tenant_id", "wa_id", name="uq_contacts_tenant_id_wa_id"),
    )
    op.create_index("ix_contacts_tenant_id", "contacts", ["tenant_id"])

    op.create_table(
        "conversations",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("contact_id", sa.UUID(), nullable=False),
        sa.Column("channel_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(20), server_default="open", nullable=False),
        sa.Column("last_inbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assigned_user_id", sa.UUID(), nullable=True),
        *_ts_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_conversations_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["contact_id"],
            ["contacts.id"],
            name="fk_conversations_contact_id_contacts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["whatsapp_accounts.id"],
            name="fk_conversations_channel_id_whatsapp_accounts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_user_id"],
            ["users.id"],
            name="fk_conversations_assigned_user_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_conversations"),
    )
    op.create_index("ix_conversations_tenant_id", "conversations", ["tenant_id"])
    op.create_index("ix_conversations_tenant_id_status", "conversations", ["tenant_id", "status"])
    op.create_index(
        "ix_conversations_tenant_id_last_inbound_at",
        "conversations",
        ["tenant_id", "last_inbound_at"],
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("wamid", sa.String(128), nullable=True),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        *_ts_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_messages_tenant_id_tenants", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_messages_conversation_id_conversations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_messages"),
    )
    op.create_index("ix_messages_tenant_id", "messages", ["tenant_id"])
    # Único PARCIAL: un mensaje saliente en cola aún no tiene wamid, y varios
    # NULL no deben colisionar. Respalda en base de datos al SETNX de Redis.
    op.create_index(
        "uq_messages_tenant_id_wamid",
        "messages",
        ["tenant_id", "wamid"],
        unique=True,
        postgresql_where=sa.text("wamid IS NOT NULL"),
    )
    op.create_index(
        "ix_messages_tenant_id_conversation_id_created_at",
        "messages",
        ["tenant_id", "conversation_id", "created_at"],
    )

    # --- knowledge ---------------------------------------------------------
    op.create_table(
        "venues",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("neighborhood", sa.String(120), nullable=True),
        sa.Column("city", sa.String(120), server_default="Medellín", nullable=False),
        sa.Column(
            "phones",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column(
            "emails",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}", nullable=False),
        *_ts_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_venues_tenant_id_tenants", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_venues"),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_venues_tenant_id_slug"),
    )
    op.create_index("ix_venues_tenant_id", "venues", ["tenant_id"])
    op.create_index("ix_venues_tenant_id_kind", "venues", ["tenant_id", "kind"])

    op.create_table(
        "rooms",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("venue_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("normalized_name", sa.String(200), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=True),
        sa.Column(
            "aliases",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        *_ts_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_rooms_tenant_id_tenants", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["venue_id"], ["venues.id"], name="fk_rooms_venue_id_venues", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rooms"),
        sa.UniqueConstraint(
            "tenant_id", "venue_id", "normalized_name", name="uq_rooms_tenant_id_venue_id_norm"
        ),
    )
    op.create_index("ix_rooms_tenant_id", "rooms", ["tenant_id"])

    # --- ingestion (antes que venue_facts/activities, que la referencian) ---
    op.create_table(
        "sources",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("cron", sa.String(80), nullable=True),
        sa.Column("venue_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        *_ts_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_sources_tenant_id_tenants", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["venue_id"], ["venues.id"], name="fk_sources_venue_id_venues", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sources"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_sources_tenant_id_name"),
    )
    op.create_index("ix_sources_tenant_id", "sources", ["tenant_id"])
    op.create_index("ix_sources_tenant_id_kind", "sources", ["tenant_id", "kind"])

    op.create_table(
        "venue_facts",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("venue_id", sa.UUID(), nullable=False),
        sa.Column("key", sa.String(80), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("source_id", sa.UUID(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confidence", sa.Float(), server_default="1.0", nullable=False),
        *_ts_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_venue_facts_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["venue_id"], ["venues.id"], name="fk_venue_facts_venue_id_venues", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name="fk_venue_facts_source_id_sources",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_venue_facts"),
    )
    op.create_index("ix_venue_facts_tenant_id", "venue_facts", ["tenant_id"])
    op.create_index(
        "ix_venue_facts_tenant_id_venue_id_key", "venue_facts", ["tenant_id", "venue_id", "key"]
    )

    op.create_table(
        "activities",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("venue_id", sa.UUID(), nullable=False),
        sa.Column("room_id", sa.UUID(), nullable=True),
        sa.Column("room_raw", sa.String(200), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("normalized_title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recurrence", sa.String(200), nullable=True),
        sa.Column("activity_group_id", sa.UUID(), nullable=True),
        sa.Column("audience", sa.String(20), nullable=True),
        sa.Column("age_min", sa.Integer(), nullable=True),
        sa.Column("age_max", sa.Integer(), nullable=True),
        sa.Column("audience_raw", sa.Text(), nullable=True),
        sa.Column("price_amount", sa.Numeric(12, 0), nullable=True),
        sa.Column("price_currency", sa.String(3), nullable=True),
        sa.Column("requires_registration", sa.Boolean(), nullable=True),
        sa.Column("registration_url", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), server_default="draft", nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_row", sa.String(120), nullable=True),
        sa.Column("evidence_snippet", sa.Text(), nullable=True),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confidence", sa.Float(), server_default="1.0", nullable=False),
        sa.Column(
            "warnings",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("extra", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by", sa.UUID(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        *_ts_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_activities_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["venue_id"], ["venues.id"], name="fk_activities_venue_id_venues", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["room_id"], ["rooms.id"], name="fk_activities_room_id_rooms", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name="fk_activities_source_id_sources",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["published_by"],
            ["users.id"],
            name="fk_activities_published_by_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_activities"),
        # Las mismas invariantes que valida la entidad del dominio, también en
        # la base: un dato malo no entra ni por SQL directo.
        sa.CheckConstraint(
            "ends_at IS NULL OR ends_at >= starts_at", name="ck_activities_ends_after_starts"
        ),
        sa.CheckConstraint(
            "age_max IS NULL OR age_min IS NULL OR age_max >= age_min",
            name="ck_activities_age_range",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_activities_confidence_range"
        ),
    )
    op.create_index("ix_activities_tenant_id", "activities", ["tenant_id"])
    # Índice principal de recuperación del bot (ADR 006).
    op.create_index(
        "ix_activities_tenant_id_venue_id_starts_at",
        "activities",
        ["tenant_id", "venue_id", "starts_at"],
    )
    op.create_index(
        "ix_activities_tenant_id_status_starts_at",
        "activities",
        ["tenant_id", "status", "starts_at"],
    )
    op.create_index(
        "ix_activities_tenant_id_activity_group_id",
        "activities",
        ["tenant_id", "activity_group_id"],
    )
    # Deduplicación del pipeline (P2A §4). Parcial: una fila borrada no debe
    # bloquear la recarga de la misma actividad.
    op.create_index(
        "uq_activities_dedupe",
        "activities",
        ["tenant_id", "venue_id", "normalized_title", "starts_at"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "activity_embeddings",
        sa.Column("activity_id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
        sa.Column("model", sa.String(80), nullable=False),
        *_ts_columns(),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["activities.id"],
            name="fk_activity_embeddings_activity_id_activities",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_activity_embeddings_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("activity_id", name="pk_activity_embeddings"),
    )
    op.create_index("ix_activity_embeddings_tenant_id", "activity_embeddings", ["tenant_id"])

    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rows_read", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rows_imported", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rows_warning", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rows_error", sa.Integer(), server_default="0", nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("stored_file_ref", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("stats", postgresql.JSONB(), server_default="{}", nullable=False),
        *_ts_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_ingestion_runs_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name="fk_ingestion_runs_source_id_sources",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ingestion_runs"),
    )
    op.create_index("ix_ingestion_runs_tenant_id", "ingestion_runs", ["tenant_id"])
    op.create_index(
        "ix_ingestion_runs_tenant_id_source_id_started_at",
        "ingestion_runs",
        ["tenant_id", "source_id", "started_at"],
    )
    op.create_index(
        "ix_ingestion_runs_tenant_id_content_hash", "ingestion_runs", ["tenant_id", "content_hash"]
    )

    # --- ai / audit --------------------------------------------------------
    op.create_table(
        "ai_traces",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=True),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("model", sa.String(80), nullable=False),
        sa.Column("tokens_in", sa.Integer(), server_default="0", nullable=False),
        sa.Column("tokens_out", sa.Integer(), server_default="0", nullable=False),
        sa.Column("latency_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cost_estimate_usd", sa.Float(), nullable=True),
        sa.Column("intent", sa.String(40), nullable=True),
        sa.Column("guardrail_retries", sa.Integer(), server_default="0", nullable=False),
        *_ts_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_ai_traces_tenant_id_tenants", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_ai_traces_conversation_id_conversations",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ai_traces"),
    )
    op.create_index("ix_ai_traces_tenant_id", "ai_traces", ["tenant_id"])
    op.create_index("ix_ai_traces_tenant_id_created_at", "ai_traces", ["tenant_id", "created_at"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("entity", sa.String(60), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=True),
        sa.Column("diff", postgresql.JSONB(), server_default="{}", nullable=False),
        *_ts_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_audit_logs_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name="fk_audit_logs_actor_id_users", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_logs"),
    )
    op.create_index("ix_audit_logs_tenant_id", "audit_logs", ["tenant_id"])
    op.create_index(
        "ix_audit_logs_tenant_id_entity_entity_id",
        "audit_logs",
        ["tenant_id", "entity", "entity_id"],
    )
    op.create_index("ix_audit_logs_tenant_id_created_at", "audit_logs", ["tenant_id", "created_at"])

    # --- Rol de aplicación --------------------------------------------------
    # Un bloque DO no admite parámetros vinculados, así que la contraseña se
    # interpola. Se escapan las comillas simples al meterla en el literal SQL y
    # se vuelve a citar con `format(%L)` dentro del EXECUTE, que es lo que
    # neutraliza cualquier carácter especial.
    password_literal = _app_role_password().replace("'", "''")
    op.execute(
        f"""
        DO $$
        DECLARE
            pwd text := '{password_literal}';
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                EXECUTE format('CREATE ROLE {APP_ROLE} LOGIN NOBYPASSRLS PASSWORD %L', pwd);
            ELSE
                EXECUTE format('ALTER ROLE {APP_ROLE} LOGIN NOBYPASSRLS PASSWORD %L', pwd);
            END IF;
        END
        $$;
        """
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON SCHEMA extensions TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}")
    # No recibe CREATE en public: el rol de runtime no puede alterar el esquema.

    # --- Row Level Security -------------------------------------------------
    # `tenants` compara contra su propio id; el resto contra tenant_id.
    # FORCE hace que la política aplique también al dueño de la tabla, que de
    # otro modo la omitiría.
    op.execute("ALTER TABLE tenants ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenants FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON tenants
            USING (id = {CURRENT_TENANT})
            WITH CHECK (id = {CURRENT_TENANT})
        """
    )

    for table in TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
                USING (tenant_id = {CURRENT_TENANT})
                WITH CHECK (tenant_id = {CURRENT_TENANT})
            """
        )


def downgrade() -> None:
    for table in (*TENANT_SCOPED_TABLES, "tenants"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")

    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {APP_ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {APP_ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA extensions FROM {APP_ROLE}")

    # Orden inverso al de creación, respetando las claves foráneas.
    op.drop_table("audit_logs")
    op.drop_table("ai_traces")
    op.drop_table("ingestion_runs")
    op.drop_table("activity_embeddings")
    op.drop_table("activities")
    op.drop_table("venue_facts")
    op.drop_table("sources")
    op.drop_table("rooms")
    op.drop_table("venues")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("contacts")
    op.drop_table("templates")
    op.drop_table("whatsapp_accounts")
    op.drop_table("users")
    op.drop_table("tenants")

    op.execute(f"DROP ROLE IF EXISTS {APP_ROLE}")

    # Ninguna extensión se elimina, por dos motivos distintos:
    # - `pgcrypto` ya venía instalada en el proyecto de Supabase y otros
    #   esquemas dependen de ella; esta migración no la creó y no le toca
    #   destruirla.
    # - `vector` sí la creó esta migración, pero borrarla es una operación
    #   global del esquema `extensions` que puede afectar a terceros. Dejarla
    #   es inocuo: no ocupa nada sin columnas que la usen, y el `upgrade` es
    #   idempotente gracias al IF NOT EXISTS.
