# DEPLOYMENT.md

> Estado: **despliegue local reproducible**. El pipeline a staging y producción se define en la fase P6 (ver [`ROADMAP.md`](./ROADMAP.md)); este documento se completa entonces.

## 1. Requisitos

- Docker Desktop (o Docker Engine) con Compose v2
- Un proyecto de **Supabase** (PostgreSQL gestionado). No hay Postgres en el compose: es un servicio externo (ADR 003).
- Para el canal de WhatsApp: cuenta de Meta Business verificada, app creada y número asignado. **Bloqueante de negocio abierto** — ver `CLAUDE.md` §11.

Para desarrollo sin Docker: Python 3.13 y Node.js 22+.

## 2. Configuración

```bash
cp .env.example .env
```

Completa al menos las cuatro variables obligatorias, o el backend no arranca (falla explícito con `ValidationError`):

| Variable | Valor |
|---|---|
| `ENVIRONMENT` | `development` \| `staging` \| `production` |
| `DATABASE_URL` | `postgresql+asyncpg://usuario:contraseña@host:5432/base` |
| `REDIS_URL` | Con Compose: `redis://redis:6379/0` |
| `APP_SECRET_KEY` | Aleatorio, ≥16 caracteres: `openssl rand -hex 32` |

Cada variable está documentada en [`.env.example`](../.env.example). **Nunca commitees `.env`.** El archivo vive en la raíz del repositorio; `Settings` lo resuelve por ruta absoluta, así que los comandos del backend funcionan igual ejecutándose desde `backend/`.

### Conectar a Supabase

Usa el **Session pooler**, no la conexión directa: `db.<ref>.supabase.co` solo publica registro AAAA (IPv6) y falla en cualquier red o plataforma sin IPv6. El host del pooler tiene la forma `aws-1-<región>.pooler.supabase.com` y el usuario es `postgres.<ref>` (no `postgres` a secas).

**Percent-encodea los caracteres especiales de la contraseña.** Un `+` literal se interpreta como espacio al parsear la URL y la autenticación falla con un error de credenciales que no sugiere la causa real: escríbelo `%2B`. Igual con `@` (`%40`), `:` (`%3A`), `/` (`%2F`) y `#` (`%23`).

## 3. Arranque local

```bash
docker compose up --build
```

Levanta cuatro servicios en la red interna `internal`:

| Servicio | Rol | Puerto en el host |
|---|---|---|
| `nginx` | Reverse proxy, cabeceras de seguridad, límite de cuerpo | `NGINX_PORT` (80) |
| `backend` | FastAPI (uvicorn) | — |
| `frontend` | Next.js standalone | — |
| `redis` | Cola y caché, volumen `redis_data` | — |

**Solo nginx expone puerto.** Todo entra por ahí:

- Panel: http://localhost/
- API: http://localhost/api/v1
- Healthcheck: http://localhost/health

### Verificar

```bash
docker compose ps          # los cuatro servicios en "healthy"
curl http://localhost/health
# {"status":"ok"}
```

### Operaciones comunes

```bash
docker compose logs -f backend      # seguir logs de un servicio
docker compose restart backend      # reiniciar tras un cambio de configuración
docker compose down                 # parar (conserva volúmenes)
docker compose down -v              # parar y BORRAR volúmenes (incluye datos de Redis)
```

## 4. Migraciones de base de datos

Todavía no hay migraciones: Alembic está configurado pero `versions/` está vacío (el modelo de datos llega en P1).

Cuando existan, desde `backend/`:

```bash
alembic upgrade head       # aplicar
alembic downgrade -1       # revertir la última
alembic current            # revisión actual
```

`alembic/env.py` toma la URL de `Settings` (variables de entorno), no del `alembic.ini` versionado. El `sqlalchemy.url` que trae el `.ini` es un placeholder inerte.

**Toda migración debe tener `upgrade` y `downgrade` reales y probados** (`CLAUDE.md` §1.8). Antes de aplicar en un entorno con datos: backup primero.

## 5. Desarrollo sin Docker

```bash
# Backend
cd backend
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"     # Windows
.venv/Scripts/uvicorn src.presentation.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

Backend en http://localhost:8000, frontend en http://localhost:3000 (sin nginx delante, así que sin las cabeceras de seguridad: no confundas ese entorno con producción).

## 6. Imágenes Docker

Ambas son **multi-stage** y corren con usuario sin privilegios:

- **Backend** (`backend/Dockerfile`): `python:3.13-slim`. Stage `builder` instala dependencias en un venv aislado en `/opt/venv`; el stage final copia solo ese venv y `src/`. Usuario `app`. Healthcheck contra `/health`.
- **Frontend** (`frontend/Dockerfile`): `node:22-alpine`. Stages `deps` → `builder` → `runtime`. Usa `output: "standalone"` de Next.js, así que la imagen final solo lleva `server.js`, `.next/static` y `public/`. Usuario `nextjs`.

## 7. Notas para producción (pendiente de P6)

Lo que **no** está resuelto todavía y bloquea un despliegue real:

- **TLS.** La config de nginx escucha en 80 sin HTTPS. Falta terminación TLS, redirección desde HTTP y activar `Strict-Transport-Security` (la línea está comentada en `infra/nginx/conf.d/default.conf`).
- **CSP endurecida.** Hoy incluye `unsafe-inline` y `unsafe-eval` por Next.js; hay que pasar a nonces.
- **`CORS_ORIGINS`** restringido a los dominios reales.
- **Secretos** generados aleatoriamente y distintos por entorno; ninguno reutilizado de desarrollo.
- **Backups de PostgreSQL** automáticos, con restauración probada y documentada.
- **Observabilidad**: métricas Prometheus, alertas de webhook fallido, de ingesta sin correr y de tasa de fallback alta.
- **Pipeline de despliegue** con entornos staging y producción, migraciones automáticas y rollback documentado.

Checklist completa en [`SECURITY.md`](./SECURITY.md) §11.

## 8. Diagnóstico

| Síntoma | Causa probable |
|---|---|
| `docker compose up` falla en `backend` con `ValidationError` | Falta una variable obligatoria en `.env`. El mensaje dice cuál. |
| `nginx` no arranca | Depende de que `backend` y `frontend` estén *healthy*. Revisa `docker compose ps` y los logs de esos servicios. |
| `/health` responde pero el panel no carga | Problema del frontend, no del backend: `docker compose logs frontend`. |
| El backend no conecta a Redis | `REDIS_URL` debe ser `redis://redis:6379/0` (nombre del servicio), no `localhost`, dentro de Compose. |
| El backend no conecta a la base | `DATABASE_URL` apunta a Supabase, un host externo. Verifica credenciales y que el driver sea `postgresql+asyncpg`. |
