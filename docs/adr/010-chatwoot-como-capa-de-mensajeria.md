# ADR 010 — Chatwoot como capa de mensajería e inbox, en vez de webhook y panel propios

- **Fecha:** 2026-08-04
- **Estado:** propuesto — pendiente de decisión
- **Revisa a:** no deroga ningún ADR aceptado. Acota el alcance de lo que falta construir de P3 en adelante (§11 de `CLAUDE.md`) y de la sección "Panel: inbox" pendiente.

## Contexto

El bot conversacional todavía no existe. Lo que sí existe y está probado (196 tests en verde) es la ingesta de Excel y el dominio de conocimiento (`venues`, `activities`, `venue_facts`, `pgvector`). De la capa de mensajería solo está construido el **lado de recepción**:

- `backend/src/presentation/routers/webhooks.py` — verificación HMAC del webhook de Meta, handshake `GET`, y `POST` que guarda mensajes entrantes.
- `backend/src/application/messaging/receive_inbound.py` — parseo del sobre de Meta, idempotencia por `wamid`, resolución de contacto y conversación.
- `backend/src/domain/ports/messaging.py` — el puerto `MessagingPort` (`send_text`, `send_template`, `send_interactive`, `mark_as_read`) está **definido pero sin adaptador**.

Lo que falta y aparece en §11 como "Siguiente": adaptador de envío a Meta, `AnthropicAdapter`, orquestador conversacional, aplicación real de la ventana de 24 h, y el panel de inbox para agentes humanos (`frontend/app/(inbox)/` existe como carpeta vacía con un `.gitkeep`, sin una sola pantalla).

La pregunta que se plantea es si esa parte pendiente —envío, ventana de 24 h, plantillas, persistencia de conversación/contacto, UI de inbox y escalamiento a humano— conviene seguir construyéndola a mano, o delegarla a Chatwoot (self-hosted, MIT) y quedarnos solo con el conocimiento y la IA.

## Investigación

**Agent Bot API de Chatwoot** (`developers.chatwoot.com`, `chatwoot.com/hc`): se crea un bot con `POST /platform/api/v1/agent_bots` (token de plataforma), con `name`, `outgoing_url` (webhook propio) y `account_id`; Chatwoot devuelve un `access_token` para ese bot. Al asignar el bot a un inbox desde su configuración, las conversaciones de ese inbox entran en estado `pending` automáticamente — el bot puede responder antes de que un humano se entere. Chatwoot manda eventos (`message_created`, etc.) al `outgoing_url`, firmados con `X-Chatwoot-Signature` (HMAC verificable con el secreto del bot — mismo patrón que ya implementamos para Meta). El bot responde llamando el endpoint de creación de mensajes con su `access_token`. Para escalar a humano: el bot cambia el estado de la conversación de `pending` a `open` vía la API de conversaciones, y queda disponible para asignación.

**Canal de WhatsApp Cloud API oficial**: Chatwoot soporta Embedded Signup nativo (Settings → Inboxes → WhatsApp → "Connect with WhatsApp Business"), que hace el flujo completo de Meta (WABA, número, credenciales) sin tocar tokens a mano. Internamente ya resuelve verificación de firma, ventana de 24 h y fallback a plantilla — es exactamente lo que `MessagingPort` todavía no tiene implementado.

**Límite de multi-tenencia encontrado** (relevante porque el proyecto es una plataforma SaaS multitenant, no solo el bot de EPM): el modelo de `Account` de Chatwoot aísla bien conversaciones/contactos/inboxes por `account_id` a nivel de base de datos. Pero la integración de WhatsApp Embedded Signup se configura a **nivel de instancia** (`WHATSAPP_APP_ID`, `WHATSAPP_CONFIGURATION_ID`, `WHATSAPP_APP_SECRET` son variables globales de un único App de Meta), y no hay enrutamiento interno por `phone_number_id` entre cuentas — confirmado por el issue abierto `chatwoot/chatwoot#13426` ("Multi-tenant support for WhatsApp Embedded in Chatwoot"). El **flujo de alta con un clic (Embedded Signup)** no está resuelto para multi-tenant; el modelo de datos por debajo sí lo soporta si cada inbox se configura **manualmente** con su propio `phone_number_id` y token (flujo "manual" documentado, no el embebido).

## Decisión propuesta

**1. Chatwoot (self-hosted) pasa a ser dueño de todo el canal de WhatsApp y del inbox humano**: handshake y firma del webhook de Meta, ventana de 24 h, plantillas, persistencia de `contacts`/`conversations`/`messages`, y la UI de agentes para escalamiento.

**2. El backend actual se reduce a lo que ya es su fortaleza probada**: ingesta de Excel, dominio de conocimiento (`KnowledgeRetrieverPort`), y se le agrega el `AnthropicAdapter` que faltaba. Se conecta a Chatwoot como un **Agent Bot**: un endpoint que recibe `message_created`, verifica `X-Chatwoot-Signature`, resuelve tenant, llama `KnowledgeRetrieverPort` + `AIProviderPort`, y responde vía la API de mensajes de Chatwoot. Si aplica una regla de escalamiento (§7 de `CLAUDE.md`), cambia la conversación a `open` en vez de responder.

**3. Se retira del alcance**: la implementación de `MessagingPort` contra Meta directamente, la lógica propia de ventana de 24 h sobre `conversations.window_expires_at`, y el panel de inbox en `frontend/app/(inbox)/` (Chatwoot trae su propia UI de agente).

**4. Se mantiene sin cambios**: todo el pipeline de ingesta de Excel, el modelo `venues`/`rooms`/`activities`/`venue_facts`/`activity_embeddings`, y el panel `/programacion` ya construido.

**5. Nueva pieza a construir**: tabla de mapeo `tenant_id ↔ chatwoot_account_id`/`inbox_id` (reemplaza en ese rol a `whatsapp_accounts`, que hoy resuelve tenant por `phone_number_id`).

## Razones

Lo que falta construir en la capa de mensajería (envío, ventana de 24 h, plantillas, UI de inbox con escalamiento) es exactamente lo que Chatwoot ya tiene en producción desde hace años, probado por miles de instalaciones — construirlo a mano es reinventar un producto maduro para llegar al mismo lugar, con más superficie de bugs propios. Lo que sí es diferencial y no existe en Chatwoot es el dominio de conocimiento de la Fundación (Excel determinista, `pgvector`, reglas de negocio de §7) — eso se conserva intacto.

No se pierde trabajo ya hecho: la verificación HMAC del webhook y la idempotencia por `wamid` en `receive_inbound.py` no se tiran, se reescriben con la misma forma contra `X-Chatwoot-Signature` en vez de `X-Hub-Signature-256` — es el mismo patrón, otro emisor.

## Consecuencias

**Positivas**

- Se deja de construir: adaptador de envío a Meta, aplicación de ventana de 24 h, manejo de plantillas, y todo el panel de inbox (`frontend/app/(inbox)/`) — probablemente el bloque de trabajo más grande que quedaba pendiente.
- Chatwoot MIT self-hosted: sin costo de licencia ni por asiento.
- El equipo de comunicaciones de la Fundación obtiene gratis una bandeja de entrada multiagente con historial, notas internas y asignación — algo que el panel propio no iba a tener en el corto plazo.

**Negativas y riesgos**

- **Suma Ruby on Rails + Sidekiq + su propio Postgres/Redis** a una infraestructura hoy Python/Next — una pieza más para operar, aunque el `docker-compose.yml` actual ya tiene Redis y el patrón de contenedores para sumar un servicio más.
- **El límite de multi-tenencia de WhatsApp** (arriba) importa solo si hay planes concretos de un segundo tenant pagando pronto: con EPM como tenant único, configurar su inbox manualmente no es un problema; se vuelve relevante recién al escalar a SaaS multi-cliente con alta autoservicio.
- `whatsapp_accounts`, `conversations`, `messages` y la lógica de `ConversationWindow` en el dominio quedan huérfanas o cambian de rol — hay que decidir explícitamente si se conservan para trazabilidad/`ai_traces` propia o si se vive con lo que expone la API de Chatwoot.
- Dependencia de la disponibilidad y los ciclos de release de un proyecto externo para todo lo que toca WhatsApp.

## Alternativas descartadas (por ahora)

- **Terminar el `MessagingPort` propio y construir el panel de inbox a mano.** Es la opción de más control y cero dependencias externas, pero es también el tramo de trabajo pendiente más grande y menos diferenciador: ventana de 24 h, plantillas y UI de agente son problemas ya resueltos por Chatwoot.
- **Usar Chatwoot Cloud (hosted) en vez de self-hosted.** Evita operar Rails/Sidekiq, pero introduce costo recurrente por conversación/agente y menos control sobre datos de contactos colombianos (Ley 1581) — descartado mientras no se evalúe el proveedor y su tratamiento de datos.

## Preguntas abiertas antes de implementar

1. ¿EPM sigue siendo tenant único por un tiempo, o ya hay un segundo cliente en conversación? Determina si el límite de multi-tenencia de WhatsApp de Chatwoot bloquea algo hoy.
2. ¿El equipo de la Fundación va a operar directamente la bandeja de Chatwoot, o necesitan sí o sí el panel Next.js que ya se empezó a diseñar?
3. ¿Se acepta sumar Ruby/Rails + Postgres/Redis adicionales a la infraestructura que ya se opera, o pesa más mantener un solo stack?
4. ¿Se conservan `ai_traces`/`audit_logs` propios (costo, latencia, trazas de IA) consultando la API de Chatwoot para lo demás, o se depende de lo que Chatwoot reporte?

## Referencias

- `backend/src/presentation/routers/webhooks.py`, `backend/src/application/messaging/receive_inbound.py`, `backend/src/domain/ports/messaging.py` — lo ya construido en el lado de recepción
- `CLAUDE.md` §3.4 (flujo de mensaje entrante), §3.6 (ventana de 24 h), §7 (reglas del bot y escalamiento), §11 (estado y pendientes)
- Chatwoot — [Agent Bots (guía de usuario)](https://www.chatwoot.com/hc/user-guide/articles/1677497472-how-to-use-agent-bots), [Create an Agent Bot (API)](https://developers.chatwoot.com/api-reference/agentbots/create-an-agent-bot), [WhatsApp Embedded Signup](https://developers.chatwoot.com/self-hosted/configuration/features/integrations/whatsapp-embedded-signup)
- [`chatwoot/chatwoot#13426`](https://github.com/chatwoot/chatwoot/issues/13426) — límite de multi-tenencia en WhatsApp Embedded
