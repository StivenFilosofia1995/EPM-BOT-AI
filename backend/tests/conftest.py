"""Config compartida de pytest.

Los tests no dependen de un `.env` local: fijamos aquí valores dummy para las
variables obligatorias de `Settings`, para que `pytest` funcione igual en un
entorno de CI limpio que en una máquina de desarrollo.
"""

import os

_TEST_DEFAULTS = {
    "ENVIRONMENT": "test",
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost:5432/test",
    "REDIS_URL": "redis://localhost:6379/0",
    "APP_SECRET_KEY": "test-secret-key-not-for-real-use",
}

for _key, _value in _TEST_DEFAULTS.items():
    os.environ.setdefault(_key, _value)
