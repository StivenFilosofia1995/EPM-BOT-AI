# CLAUDE.md — Memoria permanente del proyecto

> **Lee este archivo completo antes de cualquier tarea.** Es la fuente de verdad sobre arquitectura, reglas y estado.
> **Actualízalo** al final de toda tarea que cambie arquitectura, contratos, esquema de datos o alcance. Registra el cambio en `CHANGELOG.md`.

---

## 0. Ficha del proyecto

| Campo | Valor |
|---|---|
| Nombre | `epm-wa-platform` |
| Producto | Plataforma SaaS multitenant de bots de WhatsApp Business sobre la API Oficial de Meta |
| Tenant piloto | Fundación Grupo EPM — bot de programación cultural |
| Caso de uso piloto | Responder por WhatsApp la programación mensual de Biblioteca EPM, Museo del Agua, Parque de los Deseos / Casa de la Música y las 14 UVA |
| Motor de IA piloto | Claude (Anthropic) vía `AnthropicAdapter` |
| Estado | `FASE 0 — bootstrap del monorepo completado (P0)`. Ver §11 |
| Última actualización | 2026-08-03 |

---

## 1. Reglas innegociables

1. **Solo WhatsApp Business Cloud API oficial de Meta.** Prohibido Baileys, whatsapp-web.js, WhatsApp Web, QR, ingeniería inversa o cualquier librería no oficial. Si una tarea lo requiere, se rechaza y se documenta el porqué.
2. **Multitenant estricto.** Toda tabla de negocio lleva `tenant_id`. Toda consulta lo filtra. RLS activo en Supabase. Ningún repositorio expone un método sin `tenant_id`.
3. **Sin secretos en el repositorio.** Solo `.env.example` con variables documentadas y valores vacíos.
4. **Arquitectura limpia.** `domain` no importa de `infrastructure`. La dirección de las dependencias apunta siempre hacia adentro.
5. **La IA no inventa programación.** El modelo solo redacta a partir del contexto recuperado de la base de datos. Si no hay dato, el bot lo dice y entrega el canal oficial. Prohibido completar con conocimiento paramétrico.
6. **Ninguna respuesta se envía sin `tenant_id` resuelto** desde el `phone_number_id` del webhook.
7. **Documentar antes de implementar.** Cambio de arquitectura ⇒ ADR en `docs/adr/` antes del código.
8. **Toda migración es reversible** (`upgrade` y `downgrade` reales, probados).
9. **Datos personales:** Colombia, Ley 1581 de 2012. Minimización, retención definida, aviso de privacidad en el primer contacto, canal de supresión.

---

## 2. Stack

**Backend:** Python 3.13, FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic v2, asyncio, httpx, structlog.
**Frontend:** Next.js (App Router), React, TypeScript, Tailwind, shadcn/ui.
**Datos:** Supabase — PostgreSQL + `pgvector`, Auth, Storage, Realtime, RLS.
**Mensajería:** Meta WhatsApp Cloud API, Embedded Signup, OAuth, Webhooks, Templates, Media API.
**IA:** patrón Adapter. `AnthropicAdapter` (piloto), `OpenAIAdapter`, `GeminiAdapter`. Ninguna lógica de negocio conoce el proveedor.
**Infra:** Docker, Docker Compose, NGINX, Redis (caché, rate limit, cola), GitHub Actions.

---

## 3. Arquitectura

### 3.1 Capas (backend)

```
src/
├── domain/          # Entidades, value objects, puertos (ABC). Cero dependencias externas.
├── application/     # Casos de uso, DTOs, orquestación. Depende solo de domain.
├── infrastructure/  # SQLAlchemy, Supabase, Meta, Anthropic/OpenAI/Gemini, Redis.
└── presentation/    # Routers FastAPI, schemas Pydantic, middlewares, dependencias.
```

Regla de importación verificada en CI: `domain` no importa `application`, `infrastructure` ni `presentation`.

### 3.2 Puertos principales (`domain/ports/`)

| Puerto | Responsabilidad |
|---|---|
| `MessagingPort` | Enviar mensajes/plantillas, marcar leído |
| `AIProviderPort` | `complete(messages, tools, system) -> AIResponse` |
| `KnowledgeRetrieverPort` | Recuperar actividades y hechos por tenant, espacio y fecha |
| `ConversationRepositoryPort` | Persistir conversaciones y mensajes |
| `IngestionSourcePort` | Obtener contenido crudo de una fuente |

### 3.3 Bounded contexts

`identity` (tenants, usuarios, roles) · `channels` (WABA, números, plantillas) · `conversations` (chats, mensajes, estados) · `knowledge` (espacios, actividades, hechos, embeddings) · `ingestion` (fuentes, corridas, extracciones, revisión) · `ai` (adapters, prompts, trazas) · `billing` · `audit`.

### 3.4 Flujo de un mensaje entrante

```
Meta → POST /api/v1/webhooks/whatsapp
  → verificar firma X-Hub-Signature-256 (HMAC SHA256, APP_SECRET)
  → responder 200 inmediato
  → encolar en Redis
  → worker:
      resolver tenant por phone_number_id
      idempotencia por wamid (SETNX)
      persistir mensaje entrante
      clasificar intención
      recuperar contexto (KnowledgeRetriever: filtro estructurado + búsqueda semántica)
      AIProviderPort.complete(system + contexto + historial)
      validar respuesta (longitud, no-alucinación, escalamiento)
      MessagingPort.send
      persistir salida + traza
```

### 3.5 Estrategia de conocimiento (decisión clave)

**La fuente primaria es el Excel interno de la Fundación** (ADR 009). El equipo produce la parrilla mensual en un libro con una hoja por segmento de público y encabezados estables; es estructurado, autoritativo y llega **antes** que cualquier publicación. Su contrato de entrada está en `docs/CONTRATO_EXCEL_PROGRAMACION.md`.

No existe API pública de programación. Las fuentes publicadas quedan como **respaldo y verificación**: la parrilla completa se publica como revista PDF en Issuu (`issuu.com/bibliotecaepm1`), un documento por espacio y mes; la web solo muestra 3 destacados por espacio y llegó a estar **un mes desactualizada**. Ver `KB_FUNDACION_EPM.md` §1.

Por tanto:

- **Nunca scraping en el camino caliente de la conversación.** El bot lee de PostgreSQL.
- Ingesta asíncrona: `descubrir fuente → obtener → extraer → estructurar → validar → guardar como draft → revisión humana en el panel → publicar`. Cada etapa es un caso de uso independiente; el orquestador las compone.
- **El Excel no pasa por el LLM.** Es determinista y debe serlo: que un modelo reinterprete una celda ya estructurada es riesgo sin beneficio. La estructuración con LLM (JSON validado por Pydantic) se reserva para las fuentes no estructuradas — PDF (pdfplumber, con fallback a rasterizado + visión) y HTML.
- Toda actividad guarda `source_id`, `source_url`, `extracted_at`, `confidence`, `status`.
- Precedencia en conflicto: `excel_admin` > `manual` > `issuu` > `páginas de espacio` > `página de programación`. Cuando dos fuentes discrepan se **conservan ambas versiones** y decide un humano en el panel.
- Recuperación híbrida: filtro SQL por `tenant_id + venue + rango de fechas + audiencia`, luego re-ranking semántico con `pgvector`.

### 3.6 Ventana de servicio de 24 h

Fuera de la ventana solo se envían **plantillas aprobadas**. El dominio expone `ConversationWindow.is_open()`; el caso de uso decide entre mensaje libre y plantilla. Nunca se intenta enviar texto libre fuera de ventana.

---

## 4. Modelo de datos (resumen; el detalle vive en `DATABASE.md`)

```
tenants(id, name, slug, status, settings, created_at)
users(id, tenant_id, email, role, ...)
whatsapp_accounts(id, tenant_id, waba_id, phone_number_id, display_number, token_ref, status)
templates(id, tenant_id, name, language, category, status, body)
contacts(id, tenant_id, wa_id, profile_name, consent_at, opt_out_at)
conversations(id, tenant_id, contact_id, channel_id, status, last_inbound_at, window_expires_at)
messages(id, tenant_id, conversation_id, wamid, direction, type, payload, status, error)
venues(id, tenant_id, slug, name, kind, address, phones, emails, geo, metadata)
venue_facts(id, tenant_id, venue_id, key, value, valid_from, valid_to, source_id, confidence)
activities(id, tenant_id, venue_id, title, description, starts_at, ends_at, recurrence,
           audience, price, requires_registration, registration_url, status, source_id, confidence)
activity_embeddings(activity_id, embedding vector(1024))
sources(id, tenant_id, kind, url, cron, reliability, last_run_at)
ingestion_runs(id, tenant_id, source_id, status, stats, started_at, finished_at, error)
ai_traces(id, tenant_id, conversation_id, provider, model, tokens_in, tokens_out, latency_ms, cost)
audit_logs(id, tenant_id, actor_id, action, entity, entity_id, diff, created_at)
```

`token_ref` es un puntero al secreto, **no** el token. Los tokens de Meta se cifran en reposo (envelope encryption); la clave vive en variable de entorno.

---

## 5. Convenciones

- Python: `ruff` + `mypy --strict`. Tipado completo. Docstrings estilo Google en público.
- Nombres: `snake_case` (Python), `camelCase` (TS), `kebab-case` (rutas y archivos front), `PascalCase` (clases y componentes).
- Commits: Conventional Commits. Ramas: `feat/`, `fix/`, `docs/`, `chore/`.
- API versionada en `/api/v1`. Errores con envoltura uniforme `{error: {code, message, details, trace_id}}`.
- Zona horaria: **todo en UTC en base de datos**, presentación en `America/Bogota`.
- Idioma de cara al usuario: español de Colombia, tuteo cordial, sin emojis excesivos (máximo 1 por mensaje).
- Tests: `pytest` + `pytest-asyncio`, `factory_boy`, `respx` para HTTP. Cobertura mínima 80 %, 100 % en `domain` y `application`.

---

## 6. Estructura del repositorio

```
epm-wa-platform/
├── backend/
│   ├── src/{domain,application,infrastructure,presentation}/
│   ├── alembic/
│   ├── tests/{unit,integration,e2e}/
│   └── pyproject.toml
├── frontend/
│   ├── app/(auth)/ (dashboard)/ (inbox)/
│   ├── components/ui/
│   └── lib/
├── infra/{nginx,docker,supabase}/
├── docs/{ARCHITECTURE,DATABASE,API,SECURITY,DEPLOYMENT,TESTING,ROADMAP,CONTRIBUTING}.md
├── docs/adr/
├── data/seeds/fundacion-epm/
├── .github/workflows/
├── docker-compose.yml
├── .env.example
├── CHANGELOG.md
└── CLAUDE.md
```

---

## 7. Reglas del bot (tenant Fundación Grupo EPM)

**Persona:** asistente de la Fundación Grupo EPM. Cordial, breve, claro. Tutea. Español de Colombia.

**Puede:** informar programación, horarios, tarifas, direcciones, requisitos de ingreso, gratuidades, cómo llegar; entregar enlaces oficiales de reserva o inscripción; escalar a un humano.

**No puede:** inventar actividades, fechas o precios; confirmar reservas o cupos; atender temas de facturación o servicios públicos de EPM (la Fundación no es EPM — derivar); dar datos de las 4 UVA operadas por el INDER; prometer disponibilidad.

**Ante ausencia de dato:** decirlo explícitamente, ofrecer el canal oficial del espacio y, si aplica, la fecha en que se publicará la parrilla. Nunca rellenar.

**Formato de respuesta en WhatsApp:** máximo ~600 caracteres; máximo 5 actividades por mensaje; cada actividad como `*Título* — día, hora · público · lugar`; cerrar con una pregunta útil o un enlace.

**Escalamiento a humano:** queja o PQRSDF, reclamo de reserva, tercer intento fallido de resolver, solicitud explícita, o detección de menor de edad pidiendo datos sensibles.

**Aviso de privacidad:** en el primer mensaje de cada contacto nuevo, una línea con la finalidad del tratamiento y el enlace a la política.

---

## 8. Seguridad

- Verificación HMAC SHA-256 de todo webhook de Meta antes de procesar. Rechazo con 403 sin filtrar información.
- `VERIFY_TOKEN` aleatorio de ≥32 bytes, distinto por entorno.
- Rate limiting por `tenant_id` y por `wa_id` en Redis.
- Tokens de larga duración de Meta cifrados en reposo; rotación documentada.
- RLS en todas las tablas con `tenant_id`; `service_role` solo en backend, jamás en el frontend.
- Logs sin PII en claro: número enmascarado (`57******1234`), contenido de mensajes solo en tabla cifrada y con retención definida.
- CORS restringido; cabeceras de seguridad en NGINX; HTTPS obligatorio.
- Dependabot + `pip-audit` + `npm audit` en CI.

---

## 9. Variables de entorno

Toda variable nueva se agrega a `.env.example` **con comentario** en el mismo commit. Bloques: base de datos, Supabase, Meta, IA, seguridad, Redis, infraestructura, observabilidad. Ver `.env.example`.

---

## 10. Decisiones registradas (ADR)

| ADR | Decisión | Motivo |
|---|---|---|
| 001 | Solo Cloud API oficial | Legalidad, políticas de Meta, sostenibilidad |
| 002 | Clean Architecture con puertos y adaptadores | Sustituir proveedor de IA o de mensajería sin tocar el negocio |
| 003 | Supabase como PostgreSQL gestionado + Auth + RLS | Aislamiento multitenant en la capa de datos, no solo en la aplicación |
| 004 | Adapter de IA neutral | Evitar acoplamiento a un proveedor; permitir A/B y fallback |
| 005 | Ingesta asíncrona con revisión humana | Las fuentes publicadas son PDFs maquetados y la web se desactualiza (ver §3.5) |
| 006 | Recuperación híbrida SQL + pgvector | Fechas y espacios son filtros duros; la semántica solo re-rankea |
| 007 | Webhook responde 200 y encola | Meta exige respuesta rápida; el procesamiento puede tardar |
| 008 | Contenido de mensajes cifrado y con retención | Ley 1581 de 2012 y minimización de datos |
| 009 | Excel interno como fuente primaria; el Excel no pasa por el LLM | Es estructurado, autoritativo y llega antes que la publicación. Revisa y acota el ADR 005 |

---

## 11. Estado actual y pendientes

**Hecho**
- [x] Investigación de fuentes de programación (ver `KB_FUNDACION_EPM.md`)
- [x] Definición de stack, capas y modelo de datos preliminar
- [x] Reglas de negocio del bot piloto
- [x] Contrato de entrada del importador de Excel (ver `docs/CONTRATO_EXCEL_PROGRAMACION.md`)
- [x] **Bootstrap del repositorio (P0)**: estructura del monorepo, backend FastAPI con `/health`, envoltura de errores y `Settings` tipadas, frontend Next.js + Tailwind + shadcn/ui, `docker-compose` con healthchecks, nginx con cabeceras de seguridad, CI (ruff, mypy --strict, pytest, pip-audit, npm audit, build de imágenes), test de arquitectura y documentación inicial. Sin lógica de negocio.

**En curso**
- [ ] Dominio, modelo de datos, migraciones iniciales + RLS (P1)

**Siguiente**
- [ ] Pipeline de ingesta (PDF Issuu + HTML + Excel)
- [ ] Adapter de Anthropic y orquestador conversacional
- [ ] Webhook de WhatsApp + Embedded Signup
- [ ] Panel: revisión de extracciones, inbox, métricas

**Bloqueantes de negocio (no técnicos)**
- [ ] Cuenta de Meta Business verificada y número asignado a la Fundación
- [ ] Autorización formal de uso de marca y datos
- [ ] Responsable del tratamiento de datos designado
- [ ] Horarios faltantes (Biblioteca general, UVA) — ver `KB_FUNDACION_EPM.md` §5

---

## 12. Cómo trabajar en este repositorio (para Claude Code)

1. Lee `CLAUDE.md`, luego el `docs/` relevante y `KB_FUNDACION_EPM.md` si la tarea toca conocimiento.
2. Analiza y **presenta un plan** antes de escribir código. No implementes sin plan aprobado.
3. Implementa por capas: `domain` → `application` → `infrastructure` → `presentation`.
4. Escribe los tests en el mismo commit que el código.
5. Actualiza documentación afectada y `CHANGELOG.md`.
6. Actualiza §11 de este archivo.
7. Si detectas contradicción entre una instrucción y este archivo, **detente y pregunta**. No improvises.
