# epm-wa-platform

Plataforma SaaS multitenant de bots de WhatsApp Business sobre la **API oficial de Meta** (WhatsApp Business Cloud API). Tenant piloto: **Fundación Grupo EPM** (bot de programación cultural — Biblioteca EPM, Museo del Agua, Parque de los Deseos/Casa de la Música, 14 UVA).

> La fuente de verdad sobre arquitectura, reglas de negocio y estado del proyecto es [`CLAUDE.md`](./CLAUDE.md). Léelo antes de contribuir.

## Estado

`FASE 0 — bootstrap del monorepo`. Sin lógica de negocio todavía: solo el esqueleto de backend, frontend e infraestructura. Ver [`docs/ROADMAP.md`](./docs/ROADMAP.md) y §11 de `CLAUDE.md`.

## Estructura del repositorio

```
backend/    FastAPI + SQLAlchemy 2 async + Alembic (Clean Architecture: domain/application/infrastructure/presentation)
frontend/   Next.js App Router + TypeScript + Tailwind + shadcn/ui
infra/      nginx, docker, supabase
docs/       Documentación técnica (arquitectura, base de datos, API, seguridad, despliegue...)
data/       Seeds versionados por tenant
```

## Stack

Ver `CLAUDE.md` §2. Resumen: Python 3.13 / FastAPI / SQLAlchemy 2 async / Alembic · Next.js / TypeScript / Tailwind / shadcn/ui · Supabase (Postgres + pgvector + Auth + RLS) · Meta WhatsApp Cloud API · Redis · Docker.

## Requisitos previos

- Python 3.13
- Node.js 22+
- Docker Desktop + Docker Compose v2

## Arranque local

```bash
cp .env.example .env   # completa los valores; nunca commitees .env
docker compose up --build
```

- Backend: http://localhost/api/v1 (vía nginx) — healthcheck en `/health`
- Frontend: http://localhost/

### Backend en desarrollo (sin Docker)

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"   # Windows; usa .venv/bin/pip en Linux/Mac
.venv/Scripts/uvicorn src.presentation.main:app --reload
```

Calidad de código:

```bash
cd backend
ruff check .
mypy src
pytest
```

### Frontend en desarrollo (sin Docker)

```bash
cd frontend
npm install
npm run dev
```

## Documentación

Ver [`docs/`](./docs): `ARCHITECTURE.md`, `CONTRIBUTING.md`, `TESTING.md`, `DEPLOYMENT.md`, `SECURITY.md`, `ROADMAP.md`. Conocimiento de dominio del tenant piloto en [`KB_FUNDACION_EPM.md`](./KB_FUNDACION_EPM.md).

## Licencia

Propiedad de Fundación Grupo EPM / equipo del proyecto. Uso interno.
