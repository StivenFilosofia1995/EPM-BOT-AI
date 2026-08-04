"""Stub de Agent Bot para el POC de ADR 010.

Antes de escribir el Agent Bot real (verificación de firma + llamada a
KnowledgeRetrieverPort/AIProviderPort + respuesta vía API de Chatwoot), este
stub solo registra lo que Chatwoot manda de verdad: forma del payload de
`message_created`, y qué cabecera de firma llega. No asumas nada del payload
hasta verlo salir por esta consola contra la instancia local.

No depende del backend del proyecto a propósito: corre aparte para no mezclar
código de POC con `src/`, que sigue Clean Architecture (CLAUDE.md §1.4).

Uso:
    pip install fastapi uvicorn
    uvicorn agent_bot_stub:app --reload --port 8090

Luego, al crear el Agent Bot en Chatwoot, `outgoing_url` debe apuntar a esta
URL desde DENTRO del contenedor de rails: en Docker Desktop (Windows/Mac) usa
    http://host.docker.internal:8090/chatwoot/agent-bot
"""

import structlog
from fastapi import FastAPI, Request

logger = structlog.get_logger()
app = FastAPI(title="chatwoot-poc-agent-bot-stub")


@app.post("/chatwoot/agent-bot")
async def receive_event(request: Request) -> dict[str, str]:
    body = await request.json()
    logger.info(
        "chatwoot_event_received",
        signature_header=request.headers.get("X-Chatwoot-Signature"),
        event=body.get("event"),
        payload=body,
    )
    return {"status": "logged"}
