"""Configuración tipada de la aplicación, cargada desde variables de entorno.

Las variables sin valor por defecto son obligatorias: si faltan, la aplicación
falla explícitamente al arrancar (ValidationError de pydantic), en vez de
arrancar con un estado inconsistente.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "staging", "production", "test"]

# El `.env` vive en la raíz del repositorio, pero los comandos del backend se
# ejecutan desde `backend/`. Se resuelve por ruta absoluta para que funcione
# desde cualquier cwd. En Docker no existe el archivo y las variables llegan
# por el entorno (env_file del compose): pydantic-settings ignora la ruta
# inexistente sin error.
_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Configuración global del backend, por bloques (ver CLAUDE.md §9)."""

    model_config = SettingsConfigDict(
        env_file=(_REPO_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Aplicación ---------------------------------------------------
    environment: Environment
    app_name: str = "epm-wa-platform"
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"

    # --- Base de datos (Supabase Postgres) -----------------------------
    #: Conexión de RUNTIME, con el rol de aplicación (`epm_app`), que NO omite
    #: RLS. Es la que usa el backend para todas sus consultas.
    database_url: str
    #: Conexión de MIGRACIONES, con un rol con privilegios de DDL (`postgres`).
    #: Solo la usan Alembic y el seed. Si falta, se cae a `database_url`, lo
    #: cual funciona en local pero no debe hacerse en producción.
    database_migration_url: str | None = None
    #: Contraseña del rol de aplicación. Solo la usa la migración inicial para
    #: crear o actualizar `epm_app`; el backend nunca la lee en runtime (ya
    #: viene embebida en `database_url`).
    app_db_password: str | None = None
    database_pool_size: int = 10
    database_echo: bool = False

    @property
    def migration_url(self) -> str:
        return self.database_migration_url or self.database_url

    # --- Supabase -------------------------------------------------------
    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_service_role_key: str | None = None

    # --- Meta / WhatsApp Cloud API ---------------------------------------
    meta_app_id: str | None = None
    #: Secreto de la app. Con él se verifica la firma HMAC SHA-256 de cada
    #: webhook. Sin él no se puede distinguir a Meta de cualquier otro que
    #: conozca la URL, así que el webhook se apaga.
    meta_app_secret: str | None = None
    #: Contraseña que inventamos nosotros y que Meta nos devuelve en el GET de
    #: verificación. No es un token de acceso de Meta.
    meta_verify_token: str | None = None
    #: Identificador del número emisor. No es el número: es lo que Meta manda
    #: en el webhook y lo que permite saber a qué tenant pertenece el mensaje.
    meta_phone_number_id: str | None = None
    meta_waba_id: str | None = None
    #: Token con el que llamamos a la Graph API para enviar. El de la pantalla
    #: de configuración caduca en 24 h; el de producción es de usuario del
    #: sistema y va cifrado en reposo.
    meta_access_token: str | None = None
    meta_graph_api_version: str = "v21.0"

    # --- Proveedores de IA ------------------------------------------------
    default_ai_provider: Literal["anthropic", "openai", "gemini"] = "anthropic"
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    gemini_api_key: str | None = None

    # --- Seguridad ----------------------------------------------------------
    app_secret_key: str = Field(min_length=16)
    token_encryption_key: str | None = None
    webhook_rate_limit_per_minute: int = 60
    #: Token TEMPORAL de las rutas de administración, hasta que P5 traiga la
    #: autenticación con Supabase. No es un sistema de autenticación: no tiene
    #: roles ni sesiones ni identidad. Sin él, las rutas se rechazan.
    admin_api_token: str | None = None
    #: Tenant que atienden las rutas de administración mientras no exista
    #: sesión de usuario de la que deducirlo.
    default_tenant_slug: str = "fundacion-epm"

    # --- Redis --------------------------------------------------------------
    redis_url: str

    # --- Infraestructura ------------------------------------------------------
    backend_port: int = 8000
    frontend_port: int = 3000

    # --- Observabilidad ---------------------------------------------------------
    sentry_dsn: str | None = None
    otel_exporter_otlp_endpoint: str | None = None

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración cacheada (una sola lectura del entorno por proceso)."""
    return Settings()
