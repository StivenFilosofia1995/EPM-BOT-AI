# CONTRIBUTING.md

> Antes de escribir código, lee [`CLAUDE.md`](../CLAUDE.md) completo. Es la fuente de verdad sobre arquitectura, reglas y estado. Si una instrucción contradice ese archivo, **detente y pregunta**.

## 1. Entorno de desarrollo

### Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"     # Windows
# .venv/bin/pip install -e ".[dev]"       # Linux / macOS
```

Los comandos del backend se ejecutan **desde `backend/`** (el paquete es `src`, importado como `src.*`):

```bash
.venv/Scripts/uvicorn src.presentation.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Todo junto

```bash
cp .env.example .env    # completa los valores
docker compose up --build
```

## 2. Antes de abrir un PR

Los tres comandos del backend deben pasar en verde, desde `backend/`:

```bash
ruff check .
mypy src tests
pytest
```

Y en el frontend:

```bash
npm run lint
npm run build
```

Es exactamente lo que corre CI ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)), así que si pasa local, pasa allá.

## 3. Convenciones de código

Detalladas en `CLAUDE.md` §5. Resumen operativo:

| Tema | Regla |
|---|---|
| Python | `ruff` + `mypy --strict`. Tipado completo, sin `Any` gratuito. Docstrings estilo Google en API pública. |
| Nombres | `snake_case` (Python), `camelCase` (TS), `kebab-case` (rutas y archivos front), `PascalCase` (clases y componentes). |
| API | Versionada en `/api/v1`. Errores con la envoltura `{error: {code, message, details, trace_id}}`. |
| Zona horaria | **UTC en base de datos**, siempre. Presentación en `America/Bogota`. |
| Idioma de usuario | Español de Colombia, tuteo cordial, máximo 1 emoji por mensaje. |

### Orden de implementación

Se implementa **por capas, de adentro hacia afuera**: `domain` → `application` → `infrastructure` → `presentation`. No se empieza por el router.

`domain` no importa de las otras capas. Lo verifica `tests/unit/test_architecture.py` en CI; si lo rompes, el build falla.

## 4. Commits y ramas

**Conventional Commits:**

```
feat(ingestion): descubrir slugs de Issuu desde la página de programación
fix(webhook): rechazar firma HMAC inválida con 403
docs(architecture): documentar la envoltura de errores
chore(deps): subir pytest a 9.0.3 por PYSEC-2026-1845
```

Prefijos de rama: `feat/`, `fix/`, `docs/`, `chore/`.

## 5. Reglas que bloquean un PR

Estas no son preferencias de estilo; violarlas significa rechazo (`CLAUDE.md` §1):

1. **Cualquier librería no oficial de WhatsApp** (Baileys, whatsapp-web.js, QR, WhatsApp Web, ingeniería inversa). Solo Cloud API oficial de Meta.
2. **Una tabla de negocio sin `tenant_id`**, o una consulta que no lo filtre, o un método de repositorio sin `tenant_id`.
3. **Un secreto en el repositorio.** Solo `.env.example` con valores vacíos.
4. **`domain` importando de capas externas.**
5. **Una migración sin `downgrade` real y probado.**
6. **Hacer que la IA complete datos de programación** con conocimiento paramétrico. Si no hay dato en la base, el bot lo dice y entrega el canal oficial.
7. **Enviar una respuesta sin `tenant_id` resuelto** desde el `phone_number_id` del webhook.

## 6. Cambios de arquitectura

Un cambio de arquitectura requiere un **ADR en [`docs/adr/`](./adr/) antes del código** (`CLAUDE.md` §7). El formato es corto: contexto, decisión, consecuencias. Los ADR ya vigentes están listados en `CLAUDE.md` §10.

## 7. Variables de entorno

Toda variable nueva se agrega a [`.env.example`](../.env.example) **con comentario, en el mismo commit** que la introduce. Si es obligatoria, se declara sin valor por defecto en `Settings` para que la app falle explícitamente cuando falte.

## 8. Al terminar una tarea

1. Tests en el mismo commit que el código (`CLAUDE.md` §12).
2. Actualiza la documentación afectada.
3. Registra el cambio en [`CHANGELOG.md`](../CHANGELOG.md).
4. Actualiza §11 de `CLAUDE.md` (estado y pendientes).
