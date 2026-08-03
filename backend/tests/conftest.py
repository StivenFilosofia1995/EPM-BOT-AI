"""Config compartida de pytest.

Los tests unitarios no necesitan base de datos, pero `Settings` sí exige sus
variables obligatorias para construirse. Se rellenan con valores dummy **solo
si no hay configuración real**.

El orden importa: pydantic-settings da prioridad a las variables de entorno
sobre el `.env`. Si aquí se fijaran los dummy incondicionalmente, taparían la
conexión real y los tests de integración se saltarían siempre, dando una falsa
sensación de suite en verde.
"""

import os

_DUMMY_DEFAULTS = {
    "ENVIRONMENT": "test",
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost:5432/test",
    "REDIS_URL": "redis://localhost:6379/0",
    "APP_SECRET_KEY": "test-secret-key-not-for-real-use",
}


def _has_real_configuration() -> bool:
    """¿Hay un .env con conexión real que debamos respetar?"""
    try:
        from src.config.settings import Settings  # noqa: PLC0415

        Settings()
    except Exception:  # noqa: BLE001 - falta configuración: usaremos los dummy
        return False
    return True


if not _has_real_configuration():
    for key, value in _DUMMY_DEFAULTS.items():
        os.environ.setdefault(key, value)
