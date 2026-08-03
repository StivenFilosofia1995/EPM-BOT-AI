# TESTING.md

## 1. Herramientas

`pytest` + `pytest-asyncio` (modo `auto`: las corrutinas de test no necesitan decorador). Para fases posteriores: `factory_boy` (fixtures de datos) y `respx` (mock de HTTP contra Meta y los proveedores de IA — **nunca red real en los tests**).

Configuración en [`backend/pyproject.toml`](../backend/pyproject.toml), sección `[tool.pytest.ini_options]`.

## 2. Cómo correr los tests

Desde `backend/`:

```bash
pytest                    # toda la suite
pytest tests/unit         # solo unitarios
pytest -k architecture    # por nombre
pytest -q                 # salida compacta
```

## 3. Organización

```
backend/tests/
├── conftest.py        Config compartida: variables de entorno dummy
├── unit/              Rápidos, sin E/S. Dominio, value objects, arquitectura.
├── integration/       Base de datos real, Redis, HTTP mockeado con respx.
└── e2e/               Flujos completos de punta a punta.
```

`conftest.py` fija valores dummy para las variables obligatorias de `Settings` (`ENVIRONMENT`, `DATABASE_URL`, `REDIS_URL`, `APP_SECRET_KEY`) usando `setdefault`. Así la suite corre igual en un CI limpio que en una máquina con `.env`, y quien quiera apuntar a otra base solo tiene que exportar la variable antes de invocar pytest.

## 4. Cobertura exigida

`CLAUDE.md` §5: **mínimo 80 % global, 100 % en `domain` y `application`**.

Las capas internas no tienen excusa: no dependen de nada externo, así que todo es testeable sin mocks. La cobertura se instrumenta cuando exista código de negocio (P1 en adelante).

## 5. El test de arquitectura

[`tests/unit/test_architecture.py`](../backend/tests/unit/test_architecture.py) es el guardián de la regla de dependencias (`CLAUDE.md` §3.1).

Recorre cada `.py` bajo `src/domain/`, parsea su AST y recolecta los módulos importados (`import X` y `from X import ...`). Si alguno empieza por `src.application`, `src.infrastructure` o `src.presentation`, el test falla e informa el archivo y el import exacto.

Se usa análisis estático (AST) y no importación en tiempo de ejecución a propósito: detecta la violación aunque el import esté dentro de una función o de un bloque condicional, y no ejecuta código del módulo.

**Si este test falla, no lo "arregles" relajando la lista de prefijos.** La violación indica que el dominio está dependiendo hacia afuera; la corrección es invertir la dependencia con un puerto en `domain/ports/`.

## 6. Qué se prueba en cada capa

| Capa | Enfoque |
|---|---|
| `domain` | Puro, sin mocks. Value objects (validación E.164, `ConversationWindow.is_open()`, rangos de fechas), invariantes de entidades. |
| `application` | Casos de uso con puertos falsos (implementaciones en memoria, no `unittest.mock`). |
| `infrastructure` | Integración real: base de datos contra Postgres, HTTP con `respx`. Aquí se prueba el **aislamiento multitenant, incluido a nivel de RLS**. |
| `presentation` | `TestClient` de FastAPI: códigos de estado, contrato de la envoltura de errores, cabeceras. |

## 7. Pruebas críticas por fase

Del roadmap, las que no son negociables:

- **P1** — Un tenant no puede leer datos de otro. Probado a nivel de aplicación **y** de RLS (con el rol no privilegiado, no con `service_role`). `alembic upgrade head` y `downgrade base` funcionan.
- **P2** — Dado un PDF de muestra, el pipeline produce actividades en `draft` con `confidence` y `evidence_snippet`. Ninguna llega a `published` sin aprobación. El pipeline no revienta si una fuente cambia o desaparece.
- **P3** — Evals de alucinación al 100 %: el bot no inventa actividades, fechas ni precios ausentes del contexto recuperado. Casos negativos obligatorios: mes sin parrilla cargada, pregunta de facturación de EPM, petición de reservar. Fuente de los casos: `KB_FUNDACION_EPM.md` §6.
- **P4** — Firma HMAC inválida ⇒ 403. `wamid` repetido ⇒ no genera doble respuesta. Tenant desconocido ⇒ descarte con log de seguridad. Ningún token en logs ni en base de datos en claro.

## 8. Reglas

1. **Sin red en los tests.** HTTP se mockea con `respx`; los PDFs y HTML de prueba viven en `fixtures/`.
2. **Sin secretos reales**, ni siquiera en fixtures.
3. Un test que falla intermitentemente se arregla o se borra; no se marca `skip` y se olvida.
4. Los tests van **en el mismo commit** que el código que prueban.
