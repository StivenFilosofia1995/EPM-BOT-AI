# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
Versionado semántico. Commits en [Conventional Commits](https://www.conventionalcommits.org/es/).

## [No publicado]

### Añadido — P4 (primer corte): webhook de WhatsApp

- **`GET /api/v1/webhooks/whatsapp`** — apretón de manos de Meta. Devuelve el `hub.challenge` en **texto plano**; envuelto en JSON, Meta no lo reconoce y la verificación falla. Sin `META_VERIFY_TOKEN` configurado responde 503, y con token equivocado 403 sin detalle.
- **`POST /api/v1/webhooks/whatsapp`** — verificación HMAC SHA-256 de `X-Hub-Signature-256` sobre el **cuerpo crudo**, con comparación en tiempo constante. Firma inválida ⇒ 403; todo lo demás ⇒ **200 siempre**, porque Meta desactiva la suscripción tras varios fallos y un error nuestro no puede costar el canal.
- **Persistencia del entrante**: contacto (alta o refresco del nombre de perfil), conversación abierta reutilizada o nueva, y mensaje. **Idempotente por `wamid`** — Meta reintenta, y un duplicado provocaría una segunda respuesta al usuario cuando exista el bot.
- **Resolución del tenant por `phone_number_id`** contra `whatsapp_accounts`, como exige CLAUDE.md §1.6. Si el número no está registrado no se guarda nada y se registra el error.
- **`python -m src.cli register-channel`** — asocia un número a un tenant. Sin esa fila el webhook no puede atribuir los mensajes.
- `Settings` gana `meta_phone_number_id`, `meta_waba_id` y `meta_access_token`.
- **22 tests** (218 en total): challenge en texto plano, token y modo equivocados, cinco formas de firma inválida, firma de otro secreto, cuerpo alterado, error al guardar que aun así responde 200, `phone_number_id` desconocido que no guarda nada, acuses de entrega, cuerpo ilegible, y la lectura del sobre anidado de Meta.

No responde todavía: redactar la respuesta necesita el motor de IA (P3). Recibe y guarda.

> ⚠️ Con la app de Meta **sin publicar**, solo llegan los webhooks de prueba disparados desde el panel. Los mensajes reales no se entregan aunque el webhook esté bien configurado.

### Añadido — P2B (primer corte): cargar la programación desde el navegador

- **Botón para subir el Excel real.** `/programacion/importar`: selector de espacio y mes, zona de arrastrar y soltar, y **vista previa fila por fila antes de guardar nada** — semáforo por fila, motivo de cada advertencia en español y el texto literal de las celdas junto a lo interpretado. La confirmación persiste como `draft`; publicar sigue siendo un acto humano aparte (ADR 005).
- **`/programacion`** — tabla de lo cargado con filtros por espacio, mes, estado, búsqueda y «solo con advertencias», paginada en servidor.
- **API del panel**: `GET /venues`, `GET /activities` (filtros y paginación), `POST /programacion/import/preview` (parsea y **no escribe**), `POST /programacion/import` (persiste como `draft`, con `force` para reprocesar). Documentadas en `docs/API.md`.
- **Refactor del importador**: `preview_excel` (parsear) e `import_excel_bytes` (persistir desde memoria) separados de `import_excel`, que sigue siendo la ruta de la CLI. La vista previa no puede escribir porque no tiene por dónde.
- **Guarda `X-Admin-Token`** en todas las rutas de `/api/v1`, con comparación en tiempo constante. Sin `ADMIN_API_TOKEN` configurado las rutas responden `503`: un despliegue al que se le olvidó la variable se apaga en vez de quedar abierto. Es explícitamente temporal y se elimina en P5.
- **Proxy `/api/backend/*` en Next.js**: el token se inyecta en el servidor y nunca llega al navegador. El cuerpo se reenvía como stream, sin pasar el Excel por memoria dos veces.
- **28 tests nuevos** (196 en total): guarda de token en lectura y escritura, `503` sin token configurado, rechazo por extensión / tamaño / archivo vacío verificando además que el importador **ni siquiera se invoca**, límites de paginación, mes mal formado, y un test de integración contra Supabase que comprueba que la vista previa deja la base exactamente igual.

Verificado de punta a punta con `Programacion_Formativa Biblioteca_Julio_2026.xlsx` a través del navegador: 23 filas → 50 actividades, 1 fila en ámbar (el Semillero, con `registro_no_es_url` y `out_of_month`), todas en `draft`, ninguna publicada. Reimportar con `force` deja el total en 50: actualiza, no duplica.

> ⚠️ Un token compartido no es autenticación: no identifica a nadie ni tiene roles. **Mientras siga así, el panel no debe exponerse públicamente.**

### Añadido — P2A (primera mitad): importador de Excel

- **Parsers deterministas** del formato de la Fundación, uno por trampa del contrato: detección de encabezados por contenido (no por posición ni por nombre de hoja), fechas en español (listas, «Todos los martes de julio», rangos que cruzan de mes), horarios (**`12:00 m.` es mediodía, no medianoche**), público con rango de edad, tabla de decisión de inscripción y resolución de salas contra catálogo. No pasan por el LLM (ADR 009).
- **`XlsxProgramacionSource`** — produce un resultado por fila; un error de fila nunca aborta el archivo.
- **`import_excel`** — persiste como `draft` y registra la corrida en `ingestion_runs` con el hash del contenido. Idempotente por dos vías: no reprocesa contenido idéntico, y con `--force` actualiza en vez de duplicar. Las actividades ya publicadas no se tocan.
- **CLI** `python -m src.cli ingest` y `python -m src.cli seed`.
- **Catálogo de salas** de Biblioteca EPM en el seed. Sin él, el importador no puede resolver el campo `Lugar`.
- **94 tests nuevos** (168 en total) con los valores observados del archivo real. Criterio de aceptación verificado: **23 filas → 50 actividades en draft, 0 errores**.
- **`docs/INGESTION.md`** con el flujo, las trampas del formato y qué hacer cuando el Excel cambia.

### Cambiado

- **`docs/CONTRATO_EXCEL_PROGRAMACION.md` §7** — añadida la fila que faltaba en la tabla de decisión: cuando la columna de enlace trae texto que no es una URL (caso real: `No disponible por cúpos completados`), `registration_url` y `requires_registration` quedan nulos, el texto se conserva en `extra` y la fila se marca con `registro_no_es_url`. La tabla original asumía que un valor presente era siempre un enlace válido.
- `Settings` gana `database_migration_url` y `app_db_password`; se declaran `openpyxl`, `tzdata`, `types-openpyxl`.

### Corregido

- **`zoneinfo` fallaba en Windows** por falta de la base de datos de zonas horarias del sistema: `America/Bogota` funcionaba en Linux (CI y Docker) y reventaba en la máquina de desarrollo. Se declara `tzdata` para que el comportamiento sea idéntico en todas partes.
- La advertencia `out_of_month` se marcaba en todas las actividades de una fila cuando solo algunas caían fuera del mes. Ahora es por actividad: de las 6 fechas de «Del 23 de junio al 9 de julio», solo las 3 de junio la llevan.
- El importador hacía E/S bloqueante (leer el archivo, calcular el hash, parsear con openpyxl) dentro de una función `async`. Con la CLI daba igual, pero al llamarlo desde un endpoint HTTP en P2B habría bloqueado el servidor entero durante la carga. Va en un hilo aparte.

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
