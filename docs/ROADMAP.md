# ROADMAP.md

> El estado vigente vive en [`CLAUDE.md`](../CLAUDE.md) §11. Este documento describe el plan por fases; la secuencia de ejecución detallada está en [`PROMPTS_CLAUDE_CODE.md`](../PROMPTS_CLAUDE_CODE.md).

## Estado actual

**Fase 0 completada.** Investigación de fuentes hecha (ver `KB_FUNDACION_EPM.md`) y esqueleto del monorepo en pie: capas creadas, `/health`, contrato de errores, configuración tipada, Docker Compose, nginx, CI y documentación. **Sin lógica de negocio.**

---

## P0 — Bootstrap del repositorio ✅

Estructura del monorepo, `pyproject.toml` con ruff y `mypy --strict`, app FastAPI con `/health`, middleware de `request_id` y logging estructurado, envoltura uniforme de errores, `Settings` tipadas con fallo explícito, Next.js + Tailwind + shadcn/ui, Docker Compose con healthchecks, nginx con cabeceras de seguridad, CI y test de arquitectura.

**Criterio cumplido:** `ruff check`, `mypy` y `pytest` en verde; `/health` responde 200.

---

## P1 — Dominio, base de datos y multitenancy

Entidades y value objects (`TenantId`, `WaId` con validación E.164, `Wamid`, `ConversationWindow`, `Money`, `DateRange`, `Audience`, `Confidence`), puertos como ABC, modelos SQLAlchemy 2 async, migración inicial con `upgrade` y `downgrade` reales, extensiones `pgcrypto` y `vector`, **políticas RLS por tenant**, repositorios que inyectan el filtro de tenant, `TenantContext`, y el seed de la Fundación desde `KB_FUNDACION_EPM.md` §3.

Índices: `tenant_id` como primera columna en todo compuesto; `activities(tenant_id, venue_id, starts_at)`; único parcial en `messages(tenant_id, wamid)`.

**Criterio:** `alembic upgrade head` y `downgrade base` funcionan; un tenant no puede leer datos de otro (probado también a nivel de RLS); el seed carga sin errores. Los datos marcados "Pendiente" en `KB_FUNDACION_EPM.md` §5 **no se inventan: se omiten**.

**Entrega documental:** `docs/DATABASE.md`.

---

## P2A — Pipeline de ingesta (Excel, HTML, PDF)

El flujo `discover → fetch → extract → structure → validate → stage(draft) → review → publish`, con cada etapa como caso de uso independiente.

**Fuente primaria: el Excel interno de la Fundación**, según [`CONTRATO_EXCEL_PROGRAMACION.md`](./CONTRATO_EXCEL_PROGRAMACION.md). Es estructurado, autoritativo y llega antes que cualquier publicación. Issuu, la página oficial y las páginas de espacio quedan como **respaldo y verificación**.

Precedencia en conflicto: `excel_admin > manual > issuu > venue-pages > web-programacion`.

El Excel **no pasa por el LLM**: es determinista y debe serlo. La estructuración con LLM (JSON validado por `ActivityExtraction`) se reserva para PDF y HTML. Fechas normalizadas a UTC desde `America/Bogota`. Campo ausente ⇒ `null`: **prohibido inferir**. Cuando dos fuentes discrepan se conservan ambas versiones y decide un humano en el panel. Todo entra como `draft`.

**Criterio:** dado el Excel de muestra, lee **23 filas** y produce **50 actividades** en draft tras expandir las fechas (11 de la hoja infantil + 39 de jóvenes y adultos), con `confidence`, `evidence_snippet` y sus warnings; nada llega a `published` sin aprobación; el pipeline no revienta si una fuente cambia, si una hoja se renombra o si una fuente de red no existe.

**Entrega documental:** `docs/INGESTION.md`.

---

## P2B — Vista de administración de programación

Se adelanta desde P5 porque **es el punto de control de calidad de todo el bot**: si aquí entra un dato malo, el bot lo repite mil veces por WhatsApp.

`/programacion` con: carga de Excel (drag & drop, mapeo de columnas editable, vista previa con semáforo por fila y corrección en pantalla antes de importar, importación transaccional por lote), tabla con filtros y edición en línea, vista calendario con mover por arrastre y detección de choques de sala, cola de revisión con `evidence_snippet` contra registro estructurado lado a lado, e historial con diff campo a campo y reversión de lotes.

Depende de los endpoints de P2A.

**Criterio:** un administrador sube el Excel del mes, corrige las filas con advertencia, mueve un taller de fecha, elimina una actividad cancelada y publica el mes completo — sin salir de la interfaz, sin SQL, y dejando rastro en `audit_logs`.

---

## P3 — Adapter de IA y motor de respuesta

`AnthropicAdapter`, `OpenAIAdapter` y `GeminiAdapter` tras `AIProviderPort`, con factory por configuración del tenant, reintentos, timeout, manejo de rate limit y registro en `ai_traces`. **Cero referencias a un proveedor concreto fuera de `infrastructure/ai/`**, verificado por un test de imports.

`HybridRetriever`: filtro SQL duro (tenant, espacio, fechas, audiencia, `status='published'`) y luego re-ranking semántico con pgvector. `ResponderUseCase` clasifica intención, recupera contexto, construye el prompt y valida la salida. Prompt de sistema versionado en `src/prompts/fundacion_epm/system.md`, codificando `CLAUDE.md` §7.

**Guardarraíl anti-alucinación:** si la respuesta menciona una actividad, fecha o precio ausente del contexto recuperado, se rechaza y se reintenta con instrucción correctiva; a la segunda falla, mensaje de fallback con el canal oficial.

**Criterio:** cambiar de proveedor de IA es cambiar una variable de entorno, sin tocar `application/` ni `domain/`; las evals de alucinación pasan al 100 %.

---

## P4 — Canal WhatsApp

**Solo Cloud API oficial de Meta.** Verificación de suscripción (`hub.challenge`), webhook con **HMAC SHA-256 verificado antes de parsear**, 200 inmediato, encolado en Redis y procesamiento en worker. Parser tipado de todos los eventos (ignorar con log lo desconocido, nunca reventar). Idempotencia por `wamid`. Resolución de tenant por `phone_number_id`: si no resuelve, log de seguridad y descarte.

`MetaCloudApiClient` tras `MessagingPort` (texto, plantilla, media, botones, marcar leído, backoff ante 429 y 5xx). Gestión de la ventana de 24 h: fuera de ventana, solo plantilla aprobada. Embedded Signup con OAuth y almacenamiento **cifrado** del token vía `token_ref`.

**Criterio:** firma inválida ⇒ 403; `wamid` repetido no genera doble respuesta; ningún token en logs ni en base de datos en claro.

**Entrega documental:** `docs/API.md`, `docs/WHATSAPP.md`.

---

## P5 — Panel administrativo y bandeja

> `/programacion` y la cola de revisión se adelantaron a **P2B**. P5 no las reimplementa; las integra en la navegación, las guardas por rol y el sistema de diseño comunes.

Auth con Supabase y guardas por rol (owner, admin, agente, lector). `/inbox` estilo WhatsApp Web con Realtime, indicador de ventana de 24 h con cuenta regresiva y bloqueo de texto libre al expirar. `/venues` (CRUD de espacios y `venue_facts` con historial), `/dashboard` (métricas, incluidas las preguntas sin respuesta), `/configuracion`, `/logs`.

Accesible (foco visible, contraste AA, teclado), dark mode, responsive, estados de carga y error en todas las vistas.

**Criterio:** un agente puede tomar una conversación del bot y responder; las vistas de P2B quedan integradas y respetan las guardas por rol.

---

## P6 — Endurecimiento, observabilidad y despliegue

Rate limiting por tenant y `wa_id`, cifrado en reposo de tokens y contenido de mensajes, retención y purga por tenant, aviso de privacidad automático y opt-out (`BAJA`/`SALIR`) con registro de consentimiento (Ley 1581 de 2012). Observabilidad de punta a punta con `trace_id`, métricas Prometheus y alertas. Backups con restauración probada. Pipeline de staging y producción con rollback documentado. Pruebas de carga del webhook.

**Criterio:** checklist de `SECURITY.md` §11 al 100 %; despliegue a staging reproducible desde cero siguiendo solo `DEPLOYMENT.md`.

---

## Mantenimiento (recurrente, mensual)

Ejecutar la ingesta del mes para los cuatro grupos de espacios; reportar actividades nuevas, actualizadas, en conflicto y descartadas; revalidar `venue_facts` contra las páginas oficiales. Si una fuente cambió de estructura y el extractor falla: **documentar y proponer, no improvisar un parche**.

---

## Bloqueantes de negocio (no técnicos)

Estos no dependen del equipo de desarrollo y condicionan P4 en adelante:

- [ ] Cuenta de Meta Business verificada y número asignado a la Fundación
- [ ] Autorización formal de uso de marca y datos
- [ ] Responsable del tratamiento de datos designado (Ley 1581 de 2012)
- [ ] Horarios faltantes: Biblioteca EPM (general, no solo préstamo) y las 14 UVA — `KB_FUNDACION_EPM.md` §5
- [ ] Regla explícita de negocio para el cierre del Museo del Agua cuando el "primer día hábil de la semana" cae en festivo
