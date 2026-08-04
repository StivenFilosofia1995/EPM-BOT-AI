"""La aplicación arranca con la configuración mínima.

Este test existe por un fallo real: `redis_url` era obligatoria aunque nada
usara Redis todavía. Un despliegue sin esa variable no levantaba —
`ValidationError` en el arranque, healthcheck en rojo y ningún log útil— por
una dependencia que ni siquiera se estaba utilizando.

La regla que fija: **solo es obligatorio lo que el proceso necesita para
funcionar hoy.** Todo lo demás es opcional y falla, con un mensaje claro, en el
momento en que alguien intenta usarlo.
"""

import pytest
from pydantic import ValidationError

from src.config.settings import Settings

#: Lo único sin lo que el backend no puede hacer nada útil.
MINIMAL_ENV = {
    "ENVIRONMENT": "production",
    "DATABASE_URL": "postgresql+asyncpg://user:pass@host:5432/db",
    "APP_SECRET_KEY": "una-clave-de-al-menos-16-caracteres",
}


def _build(**overrides: str) -> Settings:
    """Construye `Settings` ignorando el `.env` del repositorio.

    Sin `_env_file=None` el archivo local rellenaría los huecos y el test
    pasaría en esta máquina mientras el despliegue sigue roto.
    """
    values = {**MINIMAL_ENV, **overrides}
    return Settings(_env_file=None, **{k.lower(): v for k, v in values.items()})  # type: ignore[arg-type]


def test_settings_build_with_the_minimum() -> None:
    settings = _build()

    assert settings.environment == "production"
    assert settings.redis_url is None
    assert settings.admin_api_token is None
    assert settings.meta_app_secret is None


def test_the_app_starts_without_redis() -> None:
    """Nada usa Redis todavía; su ausencia no puede tumbar el arranque."""
    settings = _build()

    assert settings.redis_url is None


@pytest.mark.parametrize("missing", ["DATABASE_URL", "APP_SECRET_KEY"])
def test_the_truly_required_settings_are_still_required(missing: str) -> None:
    """Lo imprescindible sí debe fallar, y pronto."""
    values = {k: v for k, v in MINIMAL_ENV.items() if k != missing}

    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None, **{k.lower(): v for k, v in values.items()})  # type: ignore[arg-type]

    assert missing.lower() in str(exc.value)


def test_migration_url_falls_back_to_the_runtime_url() -> None:
    """Sin `DATABASE_MIGRATION_URL`, se usa la de runtime.

    Es un compromiso consciente: permite arrancar, pero con el rol de
    aplicación no se pueden leer las tablas que no filtran por tenant. Por eso
    en producción las dos deben estar definidas (ver `docs/DATABASE.md` §2).
    """
    settings = _build()

    assert settings.migration_url == settings.database_url
