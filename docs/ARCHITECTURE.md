# ARCHITECTURE.md

> Este documento detalla la arquitectura implementada. Las decisiones y reglas innegociables viven en [`CLAUDE.md`](../CLAUDE.md) (§1, §3, §10); aquí no se contradicen, se desarrollan.

## 1. Visión general

`epm-wa-platform` es una plataforma **SaaS multitenant** de bots de WhatsApp Business sobre la **API oficial de Meta** (WhatsApp Business Cloud API). Un despliegue atiende a varios tenants; el aislamiento se garantiza en la capa de datos (RLS de PostgreSQL) además de en la aplicación.

```
                      ┌─────────┐
   WhatsApp  ────────▶│  nginx  │◀──────── Navegador (panel)
   (webhooks Meta)    └────┬────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
       ┌─────────────┐           ┌─────────────┐
       │   backend   │           │  frontend   │
       │  (FastAPI)  │           │  (Next.js)  │
       └──┬───────┬──┘           └─────────────┘
          │       │
          ▼       ▼
    ┌─────────┐  ┌──────────────────────┐
    │  Redis  │  │ Supabase (PostgreSQL │
    │ cola/   │  │  + pgvector + Auth   │
    │ caché   │  │  + RLS + Storage)    │
    └─────────┘  └──────────────────────┘
```

## 2. Clean Architecture en el backend

```
backend/src/
├── domain/          Entidades, value objects, puertos (ABC). Cero dependencias externas.
├── application/     Casos de uso, DTOs, orquestación. Depende solo de domain.
├── infrastructure/  SQLAlchemy, Supabase, Meta, Anthropic/OpenAI/Gemini, Redis.
└── presentation/    Routers FastAPI, schemas Pydantic, middlewares, dependencias.
```

**Regla de dependencias:** apuntan siempre hacia adentro. `domain` no importa de `application`, `infrastructure` ni `presentation`.

Esto no es una convención de buena fe: está **verificado automáticamente** por [`backend/tests/unit/test_architecture.py`](../backend/tests/unit/test_architecture.py), que recorre el AST de cada módulo de `domain/` y falla si encuentra un import prohibido. El test corre en CI en cada push y PR.

### Por qué

El objetivo declarado (ADR 002 y 004 de `CLAUDE.md` §10) es poder **sustituir el proveedor de IA o el de mensajería sin tocar la lógica de negocio**. Eso solo funciona si el negocio depende de abstracciones (`AIProviderPort`, `MessagingPort`) y no de SDKs concretos.

### Puertos principales (`domain/ports/`)

Definidos en `CLAUDE.md` §3.2. Se implementan a partir de la fase P1; en el bootstrap actual las capas existen pero están vacías.

| Puerto | Responsabilidad |
|---|---|
| `MessagingPort` | Enviar mensajes/plantillas, marcar leído |
| `AIProviderPort` | `complete(messages, tools, system) -> AIResponse` |
| `KnowledgeRetrieverPort` | Recuperar actividades y hechos por tenant, espacio y fecha |
| `ConversationRepositoryPort` | Persistir conversaciones y mensajes |
| `IngestionSourcePort` | Obtener contenido crudo de una fuente |

## 3. Capa de presentación (implementada en P0)

[`backend/src/presentation/main.py`](../backend/src/presentation/main.py) contiene solo infraestructura HTTP, sin lógica de negocio:

- **`create_app()`** — factory de la app FastAPI. Permite construir instancias aisladas en tests.
- **`/health`** — devuelve `{"status": "ok"}`. Lo consumen los healthchecks de Docker Compose y de nginx.
- **Router `/api/v1`** — montado y vacío. Los routers de negocio se cuelgan de aquí.
- **Middleware de contexto** — genera o propaga un `request_id` (respeta la cabecera `X-Request-Id` que inyecta nginx), lo ata al contexto de `structlog` y lo devuelve en la respuesta. Registra método, ruta, código y duración de cada petición en JSON.
- **CORS** — orígenes desde `CORS_ORIGINS`, restringidos por entorno.

### Envoltura de errores

Toda respuesta de error usa el mismo contrato (`CLAUDE.md` §5), implementado en [`backend/src/presentation/errors.py`](../backend/src/presentation/errors.py):

```json
{
  "error": {
    "code": "http_404",
    "message": "Not Found",
    "details": null,
    "trace_id": "b2c3d4e5-..."
  }
}
```

Hay tres handlers registrados: `HTTPException`, `RequestValidationError` (422, con `details` = errores de Pydantic) y `Exception` (500, sin filtrar el detalle interno al cliente). El `trace_id` es el mismo `request_id` de los logs, lo que permite ir de una queja del usuario a la traza exacta.

## 4. Configuración

[`backend/src/config/settings.py`](../backend/src/config/settings.py) define un único objeto `Settings` (pydantic-settings) con todos los bloques de `.env.example`. Las variables **obligatorias no tienen valor por defecto**: si faltan, la app falla al arrancar con un `ValidationError` explícito en vez de arrancar a medias.

Obligatorias hoy: `ENVIRONMENT`, `DATABASE_URL`, `REDIS_URL`, `APP_SECRET_KEY` (mínimo 16 caracteres).

Las de Supabase, Meta, proveedores de IA y observabilidad son opcionales **mientras no exista código que las use**; se vuelven obligatorias en la fase que las introduce. `get_settings()` está cacheado con `lru_cache`: una sola lectura del entorno por proceso.

## 5. Frontend

Next.js (App Router) + TypeScript + Tailwind + shadcn/ui. Grupos de rutas previstos:

- `app/(auth)/` — autenticación. Contiene `/login`.
- `app/(dashboard)/` — panel: programación, revisión de extracciones, métricas, configuración.
- `app/(inbox)/` — bandeja tipo WhatsApp Web.

El build usa `output: "standalone"` para producir una imagen Docker mínima.

## 6. Infraestructura local

`docker-compose.yml` levanta cuatro servicios en una red interna (`internal`), con healthchecks y `restart: unless-stopped`:

| Servicio | Imagen / build | Expuesto al host |
|---|---|---|
| `nginx` | `nginx:1.27-alpine` | sí, `NGINX_PORT` (80 por defecto) |
| `backend` | `./backend/Dockerfile` (multi-stage) | no |
| `frontend` | `./frontend/Dockerfile` (multi-stage) | no |
| `redis` | `redis:7-alpine`, con volumen `redis_data` | no |

**Solo nginx publica puertos.** Backend, frontend y Redis son alcanzables únicamente desde la red interna. nginx termina las peticiones, aplica cabeceras de seguridad y el límite de cuerpo (ver [`SECURITY.md`](./SECURITY.md)) y enruta: `/api/` y `/health` al backend, todo lo demás al frontend.

`nginx` depende de que `backend` y `frontend` estén **healthy**, no solo arrancados; `backend` depende de que `redis` responda a `PING`.

PostgreSQL **no** está en el compose: es Supabase gestionado (ADR 003). `DATABASE_URL` apunta al proyecto correspondiente.

## 7. Flujo de un mensaje entrante (a implementar en P4)

El diseño está fijado en `CLAUDE.md` §3.4. Puntos que condicionan la arquitectura desde ya:

1. El webhook **verifica la firma HMAC SHA-256 antes de parsear** el cuerpo.
2. Responde **200 inmediato** y encola en Redis: Meta exige respuesta rápida y el procesamiento puede tardar (por eso Redis es un servicio de primera clase, no un caché opcional).
3. El worker resuelve el `tenant_id` desde el `phone_number_id`; sin tenant resuelto no se procesa ni se responde nada.
4. Idempotencia por `wamid` (SETNX en Redis + restricción única en base de datos).

## 8. Conocimiento y ingesta (a implementar en P2)

Decisión clave, documentada en `CLAUDE.md` §3.5 y justificada en `KB_FUNDACION_EPM.md` §1: **no hay API pública de programación**. La parrilla completa se publica como revista PDF en Issuu y la web oficial llegó a estar un mes desactualizada.

Consecuencia arquitectónica: **nunca hay scraping en el camino caliente de la conversación**. El bot lee de PostgreSQL; la ingesta es un proceso asíncrono, versionado y con aprobación humana (`draft → review → published`). La recuperación es híbrida: filtro SQL duro (tenant, espacio, fechas, audiencia) y luego re-ranking semántico con `pgvector`.

## 9. Estado del bootstrap

Lo implementado en P0 es únicamente el esqueleto: capas creadas y vacías, `/health`, contrato de errores, configuración, infraestructura y CI. No hay entidades de dominio, modelos de base de datos, migraciones ni endpoints de negocio. Ver [`ROADMAP.md`](./ROADMAP.md) y §11 de `CLAUDE.md`.
