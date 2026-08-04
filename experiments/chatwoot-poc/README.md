# POC de Chatwoot — validación de ADR 010

Carpeta aislada para probar el flujo de Agent Bot descrito en
[`docs/adr/010-chatwoot-como-capa-de-mensajeria.md`](../../docs/adr/010-chatwoot-como-capa-de-mensajeria.md)
antes de decidir si se acepta. No toca el `docker-compose.yml` ni el `backend/`
del proyecto — se puede borrar esta carpeta entera sin dejar rastro si el ADR
se descarta.

**Requisito:** Docker Desktop instalado y corriendo (con backend WSL2).

## Plan de validación (de menos a más riesgo)

1. Levantar Chatwoot y crear la primera cuenta.
2. Probar el Agent Bot contra un canal simple (Website/API), **sin WhatsApp
   todavía** — así se valida el mecanismo (webhook → firma → respuesta) sin
   necesitar credenciales de Meta.
3. Recién con eso funcionando, conectar un canal de WhatsApp Cloud API real
   (flujo manual, con un número de prueba de Meta) y repetir la prueba.

Si el paso 2 falla o el modelo de datos no encaja, se descarta la migración
sin haber tocado Meta para nada.

## 1. Levantar Chatwoot

```bash
cd experiments/chatwoot-poc
cp .env.example .env
# completa SECRET_KEY_BASE (openssl rand -hex 64), POSTGRES_PASSWORD y
# REDIS_PASSWORD con cualquier valor — es un contenedor local descartable.

docker compose up -d postgres redis
docker compose run --rm rails bundle exec rails db:chatwoot_prepare
docker compose up -d
```

Espera a que `http://localhost:3010` responda (puede tardar 1-2 min en el
primer arranque). Crea la primera cuenta desde ahí — con
`ENABLE_ACCOUNT_SIGNUP=true` en `.env`, el primer registro queda como
superadmin.

## 2. Crear un inbox de prueba sin WhatsApp

Dentro de Chatwoot: **Settings → Inboxes → Add Inbox → Website** (o **API**).
Cualquiera de los dos sirve para el POC porque el Agent Bot no le importa el
canal — solo le llegan eventos de conversación.

## 3. Levantar el stub del Agent Bot (en el host, fuera de Docker)

```bash
cd experiments/chatwoot-poc
pip install fastapi uvicorn structlog
uvicorn agent_bot_stub:app --reload --port 8090
```

Este stub **solo registra** lo que llega — todavía no verifica firma ni
responde nada con sentido. El objetivo de esta primera corrida es ver la
forma real del payload de `message_created` antes de escribir el Agent Bot
de verdad contra `KnowledgeRetrieverPort` + `AnthropicAdapter`.

## 4. Crear el Agent Bot (vía consola de Rails — más simple que bootstrapear
   un Platform App para un POC de un solo uso)

```bash
docker compose exec rails bundle exec rails console
```

Dentro de la consola:

```ruby
account = Account.first
bot = AgentBot.create!(
  name: "EPM Bot POC",
  outgoing_url: "http://host.docker.internal:8090/chatwoot/agent-bot",
  account_id: account.id
)
puts bot.access_token.token   # guardalo: se usa para responder en el paso 6
```

> **Nota sobre Platform Apps:** la API pública `/platform/api/v1/agent_bots`
> (la que se documenta para automatizar esto) solo puede tocar cuentas creadas
> por el mismo Platform App, salvo que se le dé permiso manual por consola —
> ver `github.com/chatwoot/chatwoot/wiki/Building-on-Top-of-Chatwoot:-Platform-APIs`.
> Para este POC puntual, crear el bot directo por consola es más simple; si el
> ADR se acepta, automatizar la creación vía Platform API es trabajo de
> implementación, no de este POC.

## 5. Asignar el bot al inbox

En la UI: **Settings → Inboxes → (tu inbox) → Bot Configuration** → elegí
`EPM Bot POC` del dropdown y guardá. La conversación entrante debería quedar
en estado `pending` en vez de asignarse a un agente.

## 6. Mandar un mensaje de prueba

- Si el inbox es **Website**: abrí el widget de prueba que Chatwoot genera y
  escribí algo.
- Si es **API**: usa el endpoint de creación de conversación de la API pública
  de cuenta.

Revisa la consola de `uvicorn` — debería aparecer el payload completo del
evento `message_created` con la cabecera `X-Chatwoot-Signature`.

## Qué queda por hacer si el mecanismo funciona

Con el payload real ya visto:

1. Verificar la firma `X-Chatwoot-Signature` de verdad (hoy el stub la loguea
   pero no la valida).
2. Reemplazar el `print`/`log` por una llamada real a
   `KnowledgeRetrieverPort` + `AnthropicAdapter` del backend.
3. Responder con `POST /api/v1/accounts/{account_id}/conversations/{conversation_id}/messages`
   usando el `access_token` del bot.
4. Recién ahí, repetir todo el flujo con un inbox de **WhatsApp Cloud API**
   real en vez de Website/API, para confirmar que el canal oficial de Meta se
   comporta igual de cara al Agent Bot.

## Limpieza

```bash
docker compose down -v   # borra también los volúmenes (postgres/redis/storage)
```
