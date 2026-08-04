# Levantar Chatwoot en Railway (sin nada local)

Guía para cuando tengas un rato tranquilo — nada de esto es urgente. Son
clics en el dashboard de Railway, en el mismo proyecto donde ya está el
backend y el frontend desplegados.

## Antes de empezar

No hace falta resolver todavía el tema del número de WhatsApp verificado con
Meta. Eso puede ir en paralelo, con quien lleve esa gestión en la Fundación.
Esta guía solo levanta el "inbox" (Chatwoot) — se puede probar sin WhatsApp
real primero, con un canal de prueba (paso 5).

## Pasos

1. Entrá a tu proyecto de Railway (donde ya están `backend` y `frontend`).
2. **New → Database → Add PostgreSQL.** Railway lo crea solo, no hay que
   configurar nada.
3. **New → Database → Add Redis.** Igual, automático.
4. **New → Empty Service** (o "Deploy from Docker Image" si aparece esa
   opción directamente):
   - En "Source", elegí **Docker Image** y escribí: `chatwoot/chatwoot:latest`
   - Nombrale el servicio `chatwoot-rails`.
   - En **Variables**, copiá y pegá esto (Railway completa `${{...}}`
     automáticamente si el Postgres/Redis del paso 2-3 están en el mismo
     proyecto):
     ```
     RAILS_ENV=production
     NODE_ENV=production
     INSTALLATION_ENV=docker
     SECRET_KEY_BASE=<generá uno largo y random, por ejemplo con https://www.uuidgenerator.net/ pegando varios seguidos>
     FRONTEND_URL=https://<el-dominio-que-te-da-railway-para-este-servicio>
     ENABLE_ACCOUNT_SIGNUP=true
     POSTGRES_HOST=${{Postgres.PGHOST}}
     POSTGRES_USERNAME=${{Postgres.PGUSER}}
     POSTGRES_PASSWORD=${{Postgres.PGPASSWORD}}
     POSTGRES_DATABASE=${{Postgres.PGDATABASE}}
     REDIS_URL=${{Redis.REDIS_URL}}
     ```
   - En **Settings → Networking**, activá "Generate Domain" para que tenga
     una URL pública (`https://algo.up.railway.app`). Esa es la que va en
     `FRONTEND_URL` de arriba — puede que tengas que crear el servicio
     primero, ver qué dominio le tocó, y volver a editar la variable.
   - En **Settings → Deploy**, el "Custom Start Command" tiene que ser:
     ```
     bundle exec rails s -p $PORT -b 0.0.0.0
     ```
5. **Primer arranque de la base de datos** (una sola vez): en el servicio
   `chatwoot-rails`, abrí la pestaña **"Command"** / consola de Railway y
   corré:
   ```
   bundle exec rails db:chatwoot_prepare
   ```
   Si Railway no te deja abrir una consola interactiva en ese plan, avisame
   y lo resolvemos con un "one-off deploy" o un job temporal.
6. Repetí el paso 4, pero para un segundo servicio llamado `chatwoot-sidekiq`,
   mismas variables, mismo Docker Image, pero con el "Custom Start Command":
   ```
   bundle exec sidekiq -C config/sidekiq.yml
   ```
7. Cuando los tres servicios (Postgres, Redis, y los dos de Chatwoot) estén
   en verde ("Active"), entrá al dominio público de `chatwoot-rails` en el
   navegador. Ahí creás la primera cuenta (queda como administrador).

## Después de esto

Con Chatwoot ya funcionando en Railway, lo que sigue (y de esto me encargo
yo con código, no necesita nada tuyo) es conectar el "cerebro" — el mismo
mecanismo de Agent Bot que se probó en el POC local
(`experiments/chatwoot-poc/README.md`), pero apuntando a esta instancia real
en vez de a `localhost`.
