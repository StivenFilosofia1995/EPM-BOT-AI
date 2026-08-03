# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
Versionado semántico. Commits en [Conventional Commits](https://www.conventionalcommits.org/es/).

## [No publicado]

### Añadido — P1: dominio, base de datos y multitenancy

- **`domain/`**: value objects frozen (`TenantId`, `WaId` con validación E.164 y enmascarado para logs, `Wamid`, `ConversationWindow.is_open()` para la ventana de 24 h, `Money` en centavos, `DateRange`, `Audience`, `Confidence`), 12 entidades sin ORM y 5 puertos ABC (`MessagingPort`, `AIProviderPort`, `KnowledgeRetrieverPort`, `ConversationRepositoryPort`, `IngestionSourcePort`).
- **16 tablas SQLAlchemy 2 async** con `tenant_id` como primera columna de todo índice compuesto. Índices parciales para la idempotencia de webhooks (`messages` únicos por `wamid` solo cuando existe) y para la deduplicación del pipeline (ignorando las actividades borradas).
- **Migración inicial reversible** con extensiones `pgcrypto` y `pgvector`, verificada de punta a punta: `upgrade head` → `downgrade base` → `upgrade head`.
- **Rol de aplicación `epm_app`** (`NOBYPASSRLS`, sin `CREATE`) y **RLS activado y forzado** en las 16 tablas, con `USING` y `WITH CHECK` contra `app.tenant_id`. Sin tenant en contexto no se ve ninguna fila.
- **`BaseTenantRepository`** que inyecta el filtro de tenant y rechaza escrituras con un `tenant_id` ajeno, más `SqlAlchemyConversationRepository`.
- **`TenantContext`** y `tenant_session()`, que emite `SET LOCAL app.tenant_id` por transacción.
- **Seed de la Fundación** idempotente: tenant, 17 espacios y 20 `venue_facts`, todos con `source_url` y `verified_at`. Los datos marcados «Pendiente» en `KB_FUNDACION_EPM.md` §5 se omiten (horario general de la Biblioteca, horarios de las 14 UVA, correo público del Parque de los Deseos).
- **74 tests**, incluidos 8 de aislamiento multitenant ejecutados contra Supabase real con el rol de aplicación.
- **`docs/DATABASE.md`** con el esquema, las decisiones de índices y la política de RLS.

### Cambiado

- **La fuente primaria de programación pasa a ser el Excel interno de la Fundación**, no Issuu (**ADR 009**, en `docs/adr/009-excel-como-fuente-primaria.md`). El Excel es estructurado, autoritativo y llega antes que cualquier publicación; Issuu, la página oficial y las páginas de espacio quedan como respaldo y verificación.
  - Nueva precedencia en conflicto: `excel_admin > manual > issuu > venue-pages > web-programacion`. Cuando dos fuentes discrepan se conservan **ambas** versiones y decide un humano en el panel.
  - **El Excel no pasa por el LLM:** el importador es determinista (`openpyxl` + parsers del contrato). La estructuración con LLM se reserva para PDF y HTML.
  - Actualizados en consecuencia: `CLAUDE.md` §3.5 y la tabla de ADR de §10; `KB_FUNDACION_EPM.md` §1 (nuevo hallazgo H8, H4 marcado como superado) y §4 (tabla de fuentes y precedencia); `docs/ROADMAP.md`.
- **`PROMPTS_CLAUDE_CODE.md`:** la sección P2 se divide en **P2A** (pipeline de ingesta: Excel, HTML, PDF) y **P2B** (vista `/programacion` del frontend). P2B se adelanta desde P5 por ser el punto de control de calidad del bot. P5 se recorta en consecuencia: conserva inbox, dashboard, configuración y logs, y su CRUD de espacios pasa a `/venues`.
- `CONTRATO_EXCEL_PROGRAMACION.md` movido de la raíz a `docs/`, que es donde lo referencian los prompts de P2A y P2B.
- **Corregido el criterio de aceptación de P2A** contra el archivo real `Programacion_Formativa Biblioteca_Julio_2026.xlsx`: son **23 filas de datos** (8 infantil + 15 jóvenes y adultos) que producen **50 actividades** tras expandir las fechas (11 + 39), no 23 actividades. El criterio anterior confundía filas de origen con actividades resultantes y habría fallado por construcción. Verificado ejecutando la regla §3 del contrato sobre el archivo; el prompt ahora incluye el desglose de los dos casos de expansión más delicados (`Todos los martes de julio` ⇒ 4; `Del 23 de junio al 9 de julio` con `Martes y jueves` ⇒ 6, de las cuales 3 con warning `out_of_month`). Reflejado también en `docs/ROADMAP.md`.
- **Detectado un caso real no cubierto por el contrato** y añadido a P2A: la fila «Semillero de robótica intensivo» trae en la columna `Enlace de inscripción` el texto `No disponible por cúpos completados`, que no es una URL. La tabla de decisión del §7 asume que un valor presente en esa columna es un enlace válido. Pendiente de definir la regla y añadirla al contrato.

### Corregido

- `Settings` resolvía `.env` de forma relativa al directorio de trabajo, así que no lo encontraba al ejecutar los comandos del backend desde `backend/`, tal como indica `CONTRIBUTING.md`. Ahora la ruta se resuelve de forma absoluta contra la raíz del repositorio, conservando `.env` local como respaldo. Documentado en `docs/DEPLOYMENT.md`, junto con las dos trampas de conexión a Supabase: la conexión directa es solo IPv6 (hay que usar el Session pooler, `aws-1-<región>.pooler.supabase.com` con usuario `postgres.<ref>`) y los caracteres especiales de la contraseña deben ir percent-encoded en la URL.

### Añadido

- **Bootstrap del monorepo `epm-wa-platform`** (fase P0). Esqueleto listo para desarrollo, sin lógica de negocio.
- **Backend** (`backend/`): FastAPI sobre Python 3.13 con `pyproject.toml` (SQLAlchemy 2 async, Alembic, Pydantic v2, pydantic-settings, asyncpg, httpx, structlog, redis), configuración de `ruff` y `mypy --strict`.
  - `src/presentation/main.py`: app FastAPI con factory `create_app()`, endpoint `/health`, router `/api/v1` vacío, middleware que genera o propaga `request_id` y emite logs estructurados en JSON.
  - `src/presentation/errors.py`: envoltura uniforme de errores `{error: {code, message, details, trace_id}}` para `HTTPException`, errores de validación y excepciones no controladas.
  - `src/config/settings.py`: configuración tipada por bloques con `pydantic-settings`; las variables obligatorias (`ENVIRONMENT`, `DATABASE_URL`, `REDIS_URL`, `APP_SECRET_KEY`) hacen fallar el arranque si faltan.
  - Capas `domain/`, `application/`, `infrastructure/` y `presentation/` creadas según Clean Architecture.
  - Alembic inicializado en modo async, tomando la URL de `Settings`. Sin migraciones todavía (llegan en P1).
  - `tests/unit/test_architecture.py`: falla si `domain` importa de `application`, `infrastructure` o `presentation`, mediante análisis del AST.
  - `tests/unit/test_health.py`: verifica `/health` y el contrato de la envoltura de errores.
- **Frontend** (`frontend/`): Next.js 16 (App Router) + TypeScript + Tailwind v4 + shadcn/ui. Layout base en español de Colombia, grupos de rutas `(auth)`, `(dashboard)` e `(inbox)`, y página `/login` vacía. Build `standalone` para la imagen Docker.
- **Infraestructura**: `docker-compose.yml` con backend, frontend, redis y nginx — healthchecks en los cuatro, `restart: unless-stopped`, volúmenes nombrados y red interna. Solo nginx publica puerto al host. Dockerfiles multi-stage con usuario sin privilegios en ambos servicios.
- **nginx** (`infra/nginx/`): reverse proxy con cabeceras de seguridad (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, `Content-Security-Policy`), `server_tokens off` y `client_max_body_size 10m`.
- **CI** (`.github/workflows/ci.yml`): lint y tipos del backend (`ruff`, `mypy --strict`), `pytest`, lint y build del frontend, `pip-audit`, `npm audit` y build de las imágenes Docker.
- **`.env.example`** completo y comentado, sin ningún valor real, con las variables agrupadas en aplicación, base de datos, Supabase, Meta, IA, seguridad, Redis, infraestructura y observabilidad.
- **Documentación**: `README.md`, `docs/ARCHITECTURE.md`, `docs/CONTRIBUTING.md`, `docs/TESTING.md`, `docs/DEPLOYMENT.md`, `docs/SECURITY.md`, `docs/ROADMAP.md` y este `CHANGELOG.md`.

### Seguridad

- `pytest` fijado en `>=9.0.3` por **PYSEC-2026-1845** (denegación de servicio o escalada de privilegios vía el patrón de directorio `/tmp/pytest-of-{user}` en UNIX).
- `npm audit` en CI bloquea en severidad `critical`. Los tres advisories `high` presentes son transitivos de Next.js 16.2.12 (`postcss`, `sharp`) y **no tienen versión corregida upstream**: el único "arreglo" que ofrece npm es degradar a `next@9.3.3`. Quedan como paso informativo visible en CI, para revisar en cada actualización de Next.js. Ver `docs/SECURITY.md` §9.
