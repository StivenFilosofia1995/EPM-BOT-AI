-- =============================================================================
-- epm-wa-platform — esquema completo (referencia)
-- =============================================================================
--
-- ⚠️ ESTE ARCHIVO NO SE EJECUTA A MANO.
--
-- Es una VOLCADO DE REFERENCIA generado desde la migración de Alembic con:
--     cd backend && alembic upgrade head --sql
--
-- La fuente de verdad es
-- `backend/alembic/versions/0001_initial_esquema_inicial_con_rls_por_tenant.py`.
-- Para aplicar el esquema:
--     cd backend && alembic upgrade head
--
-- Ejecutarlo a mano en el editor SQL de Supabase rompe el control de versiones:
-- Alembic no se enteraría, `alembic_version` quedaría descuadrado y la
-- siguiente migración fallaría o duplicaría objetos.
--
-- ⚠️ La contraseña del rol `epm_app` está REDACTADA como
-- `__CONTRASENA_DEL_ROL__`. La real vive en APP_DB_PASSWORD del .env y nunca
-- se versiona.
--
-- Regenerar tras cada migración nueva.
-- =============================================================================

INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Generating static SQL
INFO  [alembic.runtime.migration] Will assume transactional DDL.
BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

INFO  [alembic.runtime.migration] Running upgrade  -> 0001_initial, esquema inicial con RLS por tenant
-- Running upgrade  -> 0001_initial

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions;

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;

CREATE TABLE tenants (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    name VARCHAR(200) NOT NULL, 
    slug VARCHAR(80) NOT NULL, 
    status VARCHAR(20) DEFAULT 'active' NOT NULL, 
    settings JSONB DEFAULT '{}' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_tenants PRIMARY KEY (id), 
    CONSTRAINT uq_tenants_slug UNIQUE (slug)
);

CREATE TABLE users (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    tenant_id UUID NOT NULL, 
    email TEXT NOT NULL, 
    role VARCHAR(20) NOT NULL, 
    full_name VARCHAR(200), 
    auth_user_id UUID, 
    is_active BOOLEAN DEFAULT 'true' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_users PRIMARY KEY (id), 
    CONSTRAINT fk_users_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT uq_users_tenant_id_email UNIQUE (tenant_id, email)
);

CREATE INDEX ix_users_tenant_id ON users (tenant_id);

CREATE INDEX ix_users_tenant_id_role ON users (tenant_id, role);

CREATE TABLE whatsapp_accounts (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    tenant_id UUID NOT NULL, 
    waba_id VARCHAR(64) NOT NULL, 
    phone_number_id VARCHAR(64) NOT NULL, 
    display_number VARCHAR(32) NOT NULL, 
    verified_name VARCHAR(200), 
    token_ref TEXT NOT NULL, 
    status VARCHAR(20) DEFAULT 'pending' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_whatsapp_accounts PRIMARY KEY (id), 
    CONSTRAINT fk_whatsapp_accounts_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT uq_whatsapp_accounts_phone_number_id UNIQUE (phone_number_id)
);

CREATE INDEX ix_whatsapp_accounts_tenant_id ON whatsapp_accounts (tenant_id);

CREATE INDEX ix_whatsapp_accounts_tenant_id_status ON whatsapp_accounts (tenant_id, status);

CREATE TABLE templates (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    tenant_id UUID NOT NULL, 
    name VARCHAR(200) NOT NULL, 
    language VARCHAR(10) NOT NULL, 
    category VARCHAR(40) NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    body TEXT NOT NULL, 
    components JSONB, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_templates PRIMARY KEY (id), 
    CONSTRAINT fk_templates_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT uq_templates_tenant_id_name_language UNIQUE (tenant_id, name, language)
);

CREATE INDEX ix_templates_tenant_id ON templates (tenant_id);

CREATE INDEX ix_templates_tenant_id_status ON templates (tenant_id, status);

CREATE TABLE contacts (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    tenant_id UUID NOT NULL, 
    wa_id VARCHAR(20) NOT NULL, 
    profile_name VARCHAR(200), 
    consent_at TIMESTAMP WITH TIME ZONE, 
    opt_out_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_contacts PRIMARY KEY (id), 
    CONSTRAINT fk_contacts_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT uq_contacts_tenant_id_wa_id UNIQUE (tenant_id, wa_id)
);

CREATE INDEX ix_contacts_tenant_id ON contacts (tenant_id);

CREATE TABLE conversations (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    tenant_id UUID NOT NULL, 
    contact_id UUID NOT NULL, 
    channel_id UUID NOT NULL, 
    status VARCHAR(20) DEFAULT 'open' NOT NULL, 
    last_inbound_at TIMESTAMP WITH TIME ZONE, 
    assigned_user_id UUID, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_conversations PRIMARY KEY (id), 
    CONSTRAINT fk_conversations_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT fk_conversations_contact_id_contacts FOREIGN KEY(contact_id) REFERENCES contacts (id) ON DELETE CASCADE, 
    CONSTRAINT fk_conversations_channel_id_whatsapp_accounts FOREIGN KEY(channel_id) REFERENCES whatsapp_accounts (id) ON DELETE CASCADE, 
    CONSTRAINT fk_conversations_assigned_user_id_users FOREIGN KEY(assigned_user_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_conversations_tenant_id ON conversations (tenant_id);

CREATE INDEX ix_conversations_tenant_id_status ON conversations (tenant_id, status);

CREATE INDEX ix_conversations_tenant_id_last_inbound_at ON conversations (tenant_id, last_inbound_at);

CREATE TABLE messages (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    tenant_id UUID NOT NULL, 
    conversation_id UUID NOT NULL, 
    wamid VARCHAR(128), 
    direction VARCHAR(10) NOT NULL, 
    type VARCHAR(20) NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    payload JSONB, 
    error TEXT, 
    sent_at TIMESTAMP WITH TIME ZONE, 
    delivered_at TIMESTAMP WITH TIME ZONE, 
    read_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_messages PRIMARY KEY (id), 
    CONSTRAINT fk_messages_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT fk_messages_conversation_id_conversations FOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE CASCADE
);

CREATE INDEX ix_messages_tenant_id ON messages (tenant_id);

CREATE UNIQUE INDEX uq_messages_tenant_id_wamid ON messages (tenant_id, wamid) WHERE wamid IS NOT NULL;

CREATE INDEX ix_messages_tenant_id_conversation_id_created_at ON messages (tenant_id, conversation_id, created_at);

CREATE TABLE venues (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    tenant_id UUID NOT NULL, 
    slug VARCHAR(80) NOT NULL, 
    name VARCHAR(200) NOT NULL, 
    kind VARCHAR(20) NOT NULL, 
    address TEXT, 
    neighborhood VARCHAR(120), 
    city VARCHAR(120) DEFAULT 'Medell�n' NOT NULL, 
    phones TEXT[] DEFAULT '{}'::text[] NOT NULL, 
    emails TEXT[] DEFAULT '{}'::text[] NOT NULL, 
    latitude FLOAT, 
    longitude FLOAT, 
    metadata JSONB DEFAULT '{}' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_venues PRIMARY KEY (id), 
    CONSTRAINT fk_venues_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT uq_venues_tenant_id_slug UNIQUE (tenant_id, slug)
);

CREATE INDEX ix_venues_tenant_id ON venues (tenant_id);

CREATE INDEX ix_venues_tenant_id_kind ON venues (tenant_id, kind);

CREATE TABLE rooms (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    tenant_id UUID NOT NULL, 
    venue_id UUID NOT NULL, 
    name VARCHAR(200) NOT NULL, 
    normalized_name VARCHAR(200) NOT NULL, 
    capacity INTEGER, 
    aliases TEXT[] DEFAULT '{}'::text[] NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_rooms PRIMARY KEY (id), 
    CONSTRAINT fk_rooms_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT fk_rooms_venue_id_venues FOREIGN KEY(venue_id) REFERENCES venues (id) ON DELETE CASCADE, 
    CONSTRAINT uq_rooms_tenant_id_venue_id_norm UNIQUE (tenant_id, venue_id, normalized_name)
);

CREATE INDEX ix_rooms_tenant_id ON rooms (tenant_id);

CREATE TABLE sources (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    tenant_id UUID NOT NULL, 
    kind VARCHAR(30) NOT NULL, 
    name VARCHAR(200) NOT NULL, 
    url TEXT, 
    cron VARCHAR(80), 
    venue_id UUID, 
    is_active BOOLEAN DEFAULT 'true' NOT NULL, 
    last_run_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_sources PRIMARY KEY (id), 
    CONSTRAINT fk_sources_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT fk_sources_venue_id_venues FOREIGN KEY(venue_id) REFERENCES venues (id) ON DELETE CASCADE, 
    CONSTRAINT uq_sources_tenant_id_name UNIQUE (tenant_id, name)
);

CREATE INDEX ix_sources_tenant_id ON sources (tenant_id);

CREATE INDEX ix_sources_tenant_id_kind ON sources (tenant_id, kind);

CREATE TABLE venue_facts (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    tenant_id UUID NOT NULL, 
    venue_id UUID NOT NULL, 
    key VARCHAR(80) NOT NULL, 
    value TEXT NOT NULL, 
    valid_from DATE, 
    valid_to DATE, 
    source_id UUID, 
    source_url TEXT, 
    verified_at TIMESTAMP WITH TIME ZONE, 
    confidence FLOAT DEFAULT '1.0' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_venue_facts PRIMARY KEY (id), 
    CONSTRAINT fk_venue_facts_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT fk_venue_facts_venue_id_venues FOREIGN KEY(venue_id) REFERENCES venues (id) ON DELETE CASCADE, 
    CONSTRAINT fk_venue_facts_source_id_sources FOREIGN KEY(source_id) REFERENCES sources (id) ON DELETE SET NULL
);

CREATE INDEX ix_venue_facts_tenant_id ON venue_facts (tenant_id);

CREATE INDEX ix_venue_facts_tenant_id_venue_id_key ON venue_facts (tenant_id, venue_id, key);

CREATE TABLE activities (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    tenant_id UUID NOT NULL, 
    venue_id UUID NOT NULL, 
    room_id UUID, 
    room_raw VARCHAR(200), 
    title TEXT NOT NULL, 
    normalized_title TEXT NOT NULL, 
    description TEXT, 
    starts_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    ends_at TIMESTAMP WITH TIME ZONE, 
    recurrence VARCHAR(200), 
    activity_group_id UUID, 
    audience VARCHAR(20), 
    age_min INTEGER, 
    age_max INTEGER, 
    audience_raw TEXT, 
    price_amount NUMERIC(12, 0), 
    price_currency VARCHAR(3), 
    requires_registration BOOLEAN, 
    registration_url TEXT, 
    status VARCHAR(20) DEFAULT 'draft' NOT NULL, 
    source_id UUID, 
    source_url TEXT, 
    source_row VARCHAR(120), 
    evidence_snippet TEXT, 
    extracted_at TIMESTAMP WITH TIME ZONE, 
    confidence FLOAT DEFAULT '1.0' NOT NULL, 
    warnings TEXT[] DEFAULT '{}'::text[] NOT NULL, 
    extra JSONB DEFAULT '{}' NOT NULL, 
    published_at TIMESTAMP WITH TIME ZONE, 
    published_by UUID, 
    deleted_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_activities PRIMARY KEY (id), 
    CONSTRAINT fk_activities_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT fk_activities_venue_id_venues FOREIGN KEY(venue_id) REFERENCES venues (id) ON DELETE CASCADE, 
    CONSTRAINT fk_activities_room_id_rooms FOREIGN KEY(room_id) REFERENCES rooms (id) ON DELETE SET NULL, 
    CONSTRAINT fk_activities_source_id_sources FOREIGN KEY(source_id) REFERENCES sources (id) ON DELETE SET NULL, 
    CONSTRAINT fk_activities_published_by_users FOREIGN KEY(published_by) REFERENCES users (id) ON DELETE SET NULL, 
    CONSTRAINT ck_activities_ck_activities_ends_after_starts CHECK (ends_at IS NULL OR ends_at >= starts_at), 
    CONSTRAINT ck_activities_ck_activities_age_range CHECK (age_max IS NULL OR age_min IS NULL OR age_max >= age_min), 
    CONSTRAINT ck_activities_ck_activities_confidence_range CHECK (confidence >= 0 AND confidence <= 1)
);

CREATE INDEX ix_activities_tenant_id ON activities (tenant_id);

CREATE INDEX ix_activities_tenant_id_venue_id_starts_at ON activities (tenant_id, venue_id, starts_at);

CREATE INDEX ix_activities_tenant_id_status_starts_at ON activities (tenant_id, status, starts_at);

CREATE INDEX ix_activities_tenant_id_activity_group_id ON activities (tenant_id, activity_group_id);

CREATE UNIQUE INDEX uq_activities_dedupe ON activities (tenant_id, venue_id, normalized_title, starts_at) WHERE deleted_at IS NULL;

CREATE TABLE activity_embeddings (
    activity_id UUID NOT NULL, 
    tenant_id UUID NOT NULL, 
    embedding VECTOR(1024) NOT NULL, 
    model VARCHAR(80) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_activity_embeddings PRIMARY KEY (activity_id), 
    CONSTRAINT fk_activity_embeddings_activity_id_activities FOREIGN KEY(activity_id) REFERENCES activities (id) ON DELETE CASCADE, 
    CONSTRAINT fk_activity_embeddings_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
);

CREATE INDEX ix_activity_embeddings_tenant_id ON activity_embeddings (tenant_id);

CREATE TABLE ingestion_runs (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    tenant_id UUID NOT NULL, 
    source_id UUID NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    started_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    finished_at TIMESTAMP WITH TIME ZONE, 
    rows_read INTEGER DEFAULT '0' NOT NULL, 
    rows_imported INTEGER DEFAULT '0' NOT NULL, 
    rows_warning INTEGER DEFAULT '0' NOT NULL, 
    rows_error INTEGER DEFAULT '0' NOT NULL, 
    content_hash VARCHAR(64), 
    stored_file_ref TEXT, 
    error TEXT, 
    stats JSONB DEFAULT '{}' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_ingestion_runs PRIMARY KEY (id), 
    CONSTRAINT fk_ingestion_runs_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT fk_ingestion_runs_source_id_sources FOREIGN KEY(source_id) REFERENCES sources (id) ON DELETE CASCADE
);

CREATE INDEX ix_ingestion_runs_tenant_id ON ingestion_runs (tenant_id);

CREATE INDEX ix_ingestion_runs_tenant_id_source_id_started_at ON ingestion_runs (tenant_id, source_id, started_at);

CREATE INDEX ix_ingestion_runs_tenant_id_content_hash ON ingestion_runs (tenant_id, content_hash);

CREATE TABLE ai_traces (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    tenant_id UUID NOT NULL, 
    conversation_id UUID, 
    provider VARCHAR(30) NOT NULL, 
    model VARCHAR(80) NOT NULL, 
    tokens_in INTEGER DEFAULT '0' NOT NULL, 
    tokens_out INTEGER DEFAULT '0' NOT NULL, 
    latency_ms INTEGER DEFAULT '0' NOT NULL, 
    cost_estimate_usd FLOAT, 
    intent VARCHAR(40), 
    guardrail_retries INTEGER DEFAULT '0' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_ai_traces PRIMARY KEY (id), 
    CONSTRAINT fk_ai_traces_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT fk_ai_traces_conversation_id_conversations FOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE SET NULL
);

CREATE INDEX ix_ai_traces_tenant_id ON ai_traces (tenant_id);

CREATE INDEX ix_ai_traces_tenant_id_created_at ON ai_traces (tenant_id, created_at);

CREATE TABLE audit_logs (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    tenant_id UUID NOT NULL, 
    actor_id UUID, 
    action VARCHAR(60) NOT NULL, 
    entity VARCHAR(60) NOT NULL, 
    entity_id UUID, 
    diff JSONB DEFAULT '{}' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_audit_logs PRIMARY KEY (id), 
    CONSTRAINT fk_audit_logs_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT fk_audit_logs_actor_id_users FOREIGN KEY(actor_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_audit_logs_tenant_id ON audit_logs (tenant_id);

CREATE INDEX ix_audit_logs_tenant_id_entity_entity_id ON audit_logs (tenant_id, entity, entity_id);

CREATE INDEX ix_audit_logs_tenant_id_created_at ON audit_logs (tenant_id, created_at);

DO $$
        DECLARE
            pwd text := '__CONTRASENA_DEL_ROL__';
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'epm_app') THEN
                EXECUTE format('CREATE ROLE epm_app LOGIN NOBYPASSRLS PASSWORD %L', pwd);
            ELSE
                EXECUTE format('ALTER ROLE epm_app LOGIN NOBYPASSRLS PASSWORD %L', pwd);
            END IF;
        END
        $$;;

GRANT USAGE ON SCHEMA public TO epm_app;

GRANT USAGE ON SCHEMA extensions TO epm_app;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO epm_app;

ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;

ALTER TABLE tenants FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON tenants
            USING (id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            WITH CHECK (id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE users ENABLE ROW LEVEL SECURITY;

ALTER TABLE users FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON users
                USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
                WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE whatsapp_accounts ENABLE ROW LEVEL SECURITY;

ALTER TABLE whatsapp_accounts FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON whatsapp_accounts
                USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
                WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE templates ENABLE ROW LEVEL SECURITY;

ALTER TABLE templates FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON templates
                USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
                WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE contacts ENABLE ROW LEVEL SECURITY;

ALTER TABLE contacts FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON contacts
                USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
                WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;

ALTER TABLE conversations FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON conversations
                USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
                WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE messages ENABLE ROW LEVEL SECURITY;

ALTER TABLE messages FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON messages
                USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
                WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE venues ENABLE ROW LEVEL SECURITY;

ALTER TABLE venues FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON venues
                USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
                WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE rooms ENABLE ROW LEVEL SECURITY;

ALTER TABLE rooms FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON rooms
                USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
                WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE venue_facts ENABLE ROW LEVEL SECURITY;

ALTER TABLE venue_facts FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON venue_facts
                USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
                WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE activities ENABLE ROW LEVEL SECURITY;

ALTER TABLE activities FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON activities
                USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
                WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE activity_embeddings ENABLE ROW LEVEL SECURITY;

ALTER TABLE activity_embeddings FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON activity_embeddings
                USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
                WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE sources ENABLE ROW LEVEL SECURITY;

ALTER TABLE sources FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON sources
                USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
                WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE ingestion_runs ENABLE ROW LEVEL SECURITY;

ALTER TABLE ingestion_runs FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON ingestion_runs
                USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
                WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE ai_traces ENABLE ROW LEVEL SECURITY;

ALTER TABLE ai_traces FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON ai_traces
                USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
                WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

ALTER TABLE audit_logs FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON audit_logs
                USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
                WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

INSERT INTO alembic_version (version_num) VALUES ('0001_initial') RETURNING alembic_version.version_num;

COMMIT;

