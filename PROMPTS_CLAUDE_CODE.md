# PROMPTS_CLAUDE_CODE.md — Secuencia de ejecución

> **Cómo usar:** coloca `CLAUDE.md` y `KB_FUNDACION_EPM.md` en la raíz del repositorio antes de empezar. Ejecuta un prompt por sesión, en orden. No avances si el anterior no pasa su checklist.
> **Regla transversal para todos los prompts:** *Lee `CLAUDE.md` primero. Presenta plan antes de código. Actualiza documentación, `CHANGELOG.md` y la §11 de `CLAUDE.md` al terminar.*

---

## P0 — Bootstrap del repositorio

```
Lee CLAUDE.md completo antes de actuar.

Objetivo: crear el esqueleto del monorepo `epm-wa-platform` listo para desarrollo,
sin lógica de negocio todavía.

Entrega:
1. Estructura de carpetas exacta de CLAUDE.md §6.
2. backend/: pyproject.toml (Python 3.13, FastAPI, SQLAlchemy 2 async, Alembic,
   Pydantic v2 + pydantic-settings, asyncpg, httpx, structlog, redis, pytest,
   pytest-asyncio, ruff, mypy). Configuración de ruff y mypy --strict.
3. backend/src/presentation/main.py con app FastAPI, /health, /api/v1 router vacío,
   middleware de request_id y logging estructurado, manejador global de errores con
   la envoltura {error:{code,message,details,trace_id}}.
4. backend/src/config/settings.py: settings tipadas con pydantic-settings,
   fallo explícito si falta una variable obligatoria.
5. frontend/: Next.js App Router + TypeScript + Tailwind + shadcn/ui inicializado,
   layout base y página /login vacía.
6. docker-compose.yml: backend, frontend, redis, nginx. Healthchecks, restart:
   unless-stopped, volúmenes nombrados, red interna. Dockerfiles multi-stage.
7. infra/nginx/: reverse proxy con cabeceras de seguridad y límite de body.
8. .env.example COMPLETO y comentado, sin un solo valor real.
9. .github/workflows/ci.yml: lint, mypy, tests, build de imágenes, pip-audit.
10. Documentación inicial: README.md, ARCHITECTURE.md, CONTRIBUTING.md, TESTING.md,
    DEPLOYMENT.md, SECURITY.md, CHANGELOG.md, ROADMAP.md.
11. Test de arquitectura en tests/unit/test_architecture.py que falla si `domain`
    importa de application/infrastructure/presentation.

No implementes dominio ni endpoints de negocio en este paso.

Criterio de aceptación: `docker compose up` levanta todo; /health responde 200;
`ruff check`, `mypy` y `pytest` pasan en verde.
```

---

## P1 — Dominio, base de datos y multitenancy

```
Lee CLAUDE.md (§3, §4, §8) y KB_FUNDACION_EPM.md.

Objetivo: modelo de datos completo, migraciones reversibles, RLS y el núcleo del
dominio con multitenancy estricto.

Entrega:
1. domain/entities/: Tenant, User, WhatsAppAccount, Contact, Conversation, Message,
   Venue, VenueFact, Activity, Source, IngestionRun. Dataclasses frozen, sin ORM.
2. domain/value_objects/: TenantId, WaId (validación E.164), Wamid,
   ConversationWindow (con is_open(now) según la ventana de 24 h), Money, DateRange,
   Audience (enum), Confidence (0..1).
3. domain/ports/: MessagingPort, AIProviderPort, KnowledgeRetrieverPort,
   ConversationRepositoryPort, IngestionSourcePort. ABC con tipos completos.
   NINGÚN método de repositorio puede existir sin parámetro tenant_id.
4. infrastructure/database/models/: modelos SQLAlchemy 2 async según CLAUDE.md §4.
   Índices: (tenant_id, ...) como primera columna en todos los compuestos;
   índice para activities(tenant_id, venue_id, starts_at);
   índice único parcial para messages(tenant_id, wamid).
5. Alembic: migración inicial con upgrade y downgrade REALES, extensiones
   pgcrypto y vector, y políticas RLS por tenant en todas las tablas con tenant_id.
6. infrastructure/repositories/: implementaciones async. Un repositorio base que
   inyecta el filtro de tenant y lanza excepción si falta.
7. application/: TenantContext + dependencia FastAPI que lo resuelve y lo propaga.
8. data/seeds/fundacion-epm/: seed del tenant, los 17 espacios y los venue_facts
   tomados de KB_FUNDACION_EPM.md §3, cada uno con source_url y verified_at.
   Los datos marcados como "Pendiente" en §5 NO se inventan: se omiten.
9. tests: unitarios de value objects y de aislamiento multitenant (un tenant no
   puede leer datos de otro, probado también a nivel de RLS).
10. docs/DATABASE.md con diagrama, decisiones de índices y política RLS.

Criterio de aceptación: `alembic upgrade head` y `alembic downgrade base` funcionan;
el test de aislamiento multitenant pasa; el seed carga sin errores.
```

---

## P2A — Pipeline de ingesta (Excel, HTML, PDF)

```
Lee CLAUDE.md §3.5, KB_FUNDACION_EPM.md §1 y §4, y docs/CONTRATO_EXCEL_PROGRAMACION.md
COMPLETO antes de escribir una sola línea.

CONTEXTO CRÍTICO — corrige un supuesto anterior:
La fuente primaria de programación NO es Issuu. El equipo de la Fundación produce
la parrilla mensual en un archivo Excel interno, con una hoja por segmento de
público y encabezados estables. Ese archivo es estructurado, autoritativo y llega
antes que cualquier publicación. Issuu, la página oficial y las páginas de espacio
pasan a ser fuentes de RESPALDO y de verificación.

Nueva precedencia en conflicto:
  excel_admin > manual > issuu > venue-pages > web-programacion

Sigue vigente: no existe API pública; la página oficial solo muestra 3 destacados
por espacio y puede estar hasta un mes desactualizada; los slugs de Issuu no son
deterministas.

Objetivo: pipeline asíncrono, versionado y con revisión humana obligatoria, que
convierta esas fuentes en filas de `activities` publicables.

ENTREGA

1. application/ingestion/ con el flujo, cada etapa como caso de uso independiente
   y testeable por separado:
   discover → fetch → extract → structure → validate → stage(draft) → review → publish
   Ninguna etapa conoce la siguiente. El orquestador las compone.

2. infrastructure/ingestion/sources/

   a) XlsxProgramacionSource  ← FUENTE PRIMARIA, impleméntala primero
      Implementa docs/CONTRATO_EXCEL_PROGRAMACION.md al pie de la letra:
      - Detecta la fila de encabezados escaneando las primeras 10 filas y
        exigiendo al menos 6 encabezados canónicos, normalizados (minúsculas,
        sin tildes, espacios colapsados). NO asumas que es la fila 2.
      - Reconoce las hojas por sus encabezados, NUNCA por el nombre de la hoja.
        El nombre solo es una pista para `audience`.
      - Extrae mes y año del título combinado de la fila 1
        (ej.: "Programación infantil – Julio 2026"). Es la ÚNICA fuente del año
        en todo el libro.
      - Parser de fechas en español (§3 del contrato). Debe resolver, como mínimo,
        estos casos reales: "01 de julio"; "07 y 14 de julio";
        "14, 21 y 28 de julio"; "02, 09, 16 y 23 de julio";
        "Todos los martes de julio"; "Del 23 de junio al 9 de julio".
        Una fila con N fechas produce N filas en `activities`, unidas por
        `activity_group_id`. Un rango con "Día(s)" se expande solo a esos días
        de la semana. Fecha fuera del mes de la carga: se importa con warning
        `out_of_month`, NO se descarta.
      - Parser de horario (§4). ATENCIÓN: "12:00 m." es MEDIODÍA (12:00), no
        medianoche. Acepta "p.m.", "pm", "p. m." con espacio duro incluido.
        Sin hora de fin: ends_at = null. Prohibido asumir duración.
      - Resolución de `Lugar` contra un catálogo `rooms` por espacio, con
        normalización y coincidencia difusa (§5). "Sala de Formación" y
        "Sala de Formación 3" son salas DISTINTAS. Centinelas como
        "No especificado en el documento" se convierten en null. Una sala
        desconocida NO se crea automáticamente.
      - Parser de `Público` a (audience, age_min, age_max) conservando siempre
        `audience_raw` (§6). "de 9 años en adelante" ⇒ age_min=9, age_max=null.
      - Tabla de decisión de inscripción del §7. El caso "vacío + vacío" queda
        en null y exige resolución humana: no asumas nada.
      - `evidence_snippet` = fila original serializada.
      - Reporte por fila: ok | warning | error, con el número de hoja y de fila.
        Un error de fila NUNCA aborta el archivo completo.
      Usa openpyxl con read_only=True. Soporta .xlsx y .xlsm.

   b) HtmlProgramacionSource
      Scrapea la página oficial, extrae los destacados y DESCUBRE los enlaces
      "Ver toda la programación" (los slugs de Issuu del mes). Sirve para
      verificar contra el Excel y detectar publicaciones nuevas.

   c) IssuuPdfSource
      Resuelve y descarga el PDF, extrae texto con pdfplumber; si la densidad de
      texto es insuficiente, rasteriza páginas y usa el AIProviderPort en modo
      visión. Fuente de respaldo cuando el Excel no llega a tiempo.

   d) VenuePagesSource
      Horarios, tarifas y contacto de cada espacio → venue_facts.

3. Estructurador con LLM — SOLO para fuentes no estructuradas (PDF y HTML).
   El Excel NO pasa por el LLM: es determinista y debe serlo, porque es la
   fuente autoritativa. Que un LLM reinterprete una celda ya estructurada es un
   riesgo sin beneficio.
   Para PDF/HTML: prompt que devuelve EXCLUSIVAMENTE JSON validado por el schema
   Pydantic `ActivityExtraction` (los mismos campos que produce el importador de
   Excel, §9 del contrato). Fechas normalizadas a UTC desde America/Bogota.
   Campo ausente en el texto ⇒ null. Prohibido inferir o completar.

4. Deduplicación por (tenant_id, venue_id, título normalizado, starts_at) y
   resolución de conflictos según la nueva precedencia. Cuando dos fuentes
   discrepan, se conservan AMBAS versiones y el conflicto se resuelve en el
   panel, con las dos vistas lado a lado.

5. Todo lo extraído entra como status='draft'. Solo un humano publica.
   Una fila con errores no puede pasar a published bajo ninguna ruta de código.

6. Registro completo en ingestion_runs: fuente, duración, filas leídas,
   importadas, con warning, con error, hash SHA-256 del contenido para no
   reprocesar lo idéntico, y el archivo original guardado en Supabase Storage
   con su versión.

7. Idempotencia, reintentos con backoff exponencial, timeout, respeto de
   robots.txt y User-Agent identificable (solo aplica a las fuentes de red).

8. CLI:
   python -m src.cli ingest --tenant fundacion-epm --source excel \
       --file ./parrilla.xlsx --venue biblioteca-epm --month 2026-08
   python -m src.cli ingest --tenant fundacion-epm --source all --month 2026-08
   Más la tarea programada mensual para las fuentes de red.

9. Tests con el archivo real de muestra y con HTML/PDF en fixtures. Nada de red
   en los tests. Casos obligatorios, uno por cada trampa del contrato:
   - fila con 3 fechas → 3 actividades con el mismo activity_group_id
   - "Del 23 de junio al 9 de julio" en una carga de julio → warning out_of_month
   - "Todos los martes de julio" → los martes correctos del mes
   - "10:00 a.m. a 12:00 m." → 10:00–12:00, NO 10:00–00:00
   - "Taller Infantil" y "Taller infantil" → la misma sala
   - "Sala de Formación" y "Sala de Formación 3" → salas distintas
   - "No especificado en el documento" → null
   - Inscripción vacía + enlace → requires_registration = true
   - Inscripción vacía + sin enlace → null y marcado para revisión
     (OJO: este caso NO aparece en el archivo de muestra; hace falta un fixture
     sintético.)
   - encabezados en fila 4 en lugar de fila 2 → se detectan igual
   - hoja renombrada → se reconoce por encabezados
   - columna extra desconocida → se conserva en `extra`, no rompe

   CASO REAL NO CUBIERTO POR EL CONTRATO — resuélvelo y documenta la regla:
   La fila "Semillero de robótica intensivo" trae en la columna
   "Enlace de inscripción" el texto "No disponible por cúpos completados",
   que NO es una URL. La tabla de decisión del §7 dice "vacío + presente ⇒
   requires_registration = true", pero asume que lo presente es un enlace
   válido. Define el comportamiento (propuesta: registration_url = null,
   requires_registration = null, warning `registro_no_es_url` conservando el
   texto original en `extra`, y marcado para resolución humana — NUNCA
   guardar prosa en un campo de URL), añade el caso a docs/CONTRATO_EXCEL_
   PROGRAMACION.md §7 y cúbrelo con un test.

10. docs/INGESTION.md: diagrama del flujo, tabla de fuentes con la nueva
    precedencia, qué hacer cuando el Excel cambia de formato, cuando Issuu cambia
    de maquetación, y cómo reprocesar un mes ya publicado.

CRITERIO DE ACEPTACIÓN
Dado el Excel de muestra (Programacion_Formativa Biblioteca_Julio_2026.xlsx),
el importador lee 23 filas de datos (8 en la hoja infantil + 15 en jóvenes y
adultos) y produce 50 actividades en draft tras expandir las fechas:

  hoja infantil ......... 8 filas  =>  11 actividades
  jóvenes y adultos .... 15 filas  =>  39 actividades

Desglose de los casos que más se equivocan:
  - "Todos los martes de julio" (Club de Ajedrez) => 4 actividades:
    7, 14, 21 y 28 de julio de 2026.
  - "Del 23 de junio al 9 de julio" con Día(s)="Martes y jueves"
    (Semillero de robótica) => 6 actividades: 23/06, 25/06, 30/06, 02/07,
    07/07 y 09/07. Las 3 de junio llevan warning out_of_month y NO se descartan.

Cada actividad con confidence, evidence_snippet y su warning cuando aplique.
Ninguna llega a published sin aprobación. El pipeline no revienta si una fuente
cambia, si una hoja se renombra o si una fuente de red no existe.

Si tu conteo no da 50, no ajustes el criterio: el error está en el parser de
fechas. Los números de arriba están verificados contra el archivo real.
```

---

## P2B — Vista de administración de programación (frontend)

> Depende de los endpoints de P2A. Ejecuta P2A completo y con tests en verde antes de empezar P2B. Si prefieres ver la interfaz antes, pide en P2A que exponga primero los endpoints de importación y listado, y arranca P2B contra ellos.

```
Lee CLAUDE.md §2, §5 y §7, docs/CONTRATO_EXCEL_PROGRAMACION.md y docs/API.md.

Objetivo: una vista en Next.js donde un administrador gestione la programación
mensual de punta a punta sin tocar SQL. Es el punto de control de calidad de todo
el bot: si aquí entra un dato malo, el bot lo repite mil veces por WhatsApp.

RUTA: /programacion

1. CARGA DE EXCEL — /programacion/importar
   - Zona de arrastrar y soltar (.xlsx, .xlsm). Máximo 10 MB.
   - Formulario previo obligatorio, porque estos datos NO están en el archivo:
     espacio (select desde `venues`), mes y año (se PROPONEN desde el título de
     la hoja y el operador confirma), y fuente.
   - Botón "Descargar plantilla oficial": genera el .xlsx desde el contrato, con
     los encabezados canónicos, una hoja por público, fila de ejemplo y validación
     de datos en las columnas de enum.
   - Paso de mapeo de columnas: muestra los encabezados detectados y a qué campo
     canónico se asignó cada uno, editable. Si el archivo trae una columna
     desconocida, el operador decide si ignorarla o mapearla.
   - Vista previa antes de confirmar: tabla completa de filas interpretadas con
     semáforo por fila (verde ok, ámbar warning, rojo error) y el detalle del
     motivo al pasar el cursor. Contador de resumen arriba:
     "23 filas leídas · 21 correctas · 2 con advertencia · 0 con error".
   - Filas con error se pueden corregir EN LA MISMA PANTALLA antes de importar,
     sin volver a subir el archivo.
   - La importación es transaccional por lote: o entra el lote completo, o nada.
   - Nunca se publica desde aquí. Todo entra como draft.

2. TABLA DE PROGRAMACIÓN — /programacion
   - Filtros: espacio, mes, estado (draft/published/archived), público, sala,
     fuente, "solo con advertencias".
   - Búsqueda por título.
   - Columnas ordenables. Paginación del lado del servidor.
   - Edición en línea de cualquier campo, con validación inmediata contra el
     mismo schema del backend (no dupliques reglas: exponlas desde la API).
   - Selección múltiple con acciones en lote: publicar, despublicar, archivar,
     eliminar, cambiar de sala, cambiar de público.
   - ELIMINAR: soft delete con confirmación explícita que muestra el título y la
     fecha. Papelera con restauración durante 30 días. Si la actividad pertenece
     a un activity_group_id, preguntar si se elimina solo esa fecha o todo el
     grupo.
   - DUPLICAR: copia a otra fecha, útil para replicar un taller.

3. VISTA CALENDARIO — /programacion/calendario
   - Mes, semana y día. Una columna por sala, opcional.
   - MOVER: arrastrar y soltar una actividad para cambiarle la fecha o la hora.
     Al soltar, confirmación con el cambio explícito ("15 de julio 2:00 p.m. →
     22 de julio 2:00 p.m.") antes de persistir. Si pertenece a un grupo,
     preguntar si mueve solo esa ocurrencia o todo el grupo.
   - Detección de choques: dos actividades en la misma sala y franja se marcan en
     rojo con aviso. No se bloquea el guardado, se advierte.
   - Reordenar dentro de un mismo día para controlar el orden de presentación.

4. REVISIÓN Y PUBLICACIÓN — /programacion/revision
   - Cola de drafts. Vista lado a lado: a la izquierda el evidence_snippet (la
     fila original del Excel o el fragmento del PDF con enlace a la fuente), a la
     derecha el registro estructurado editable.
   - Acciones: aprobar, aprobar con cambios, rechazar con motivo.
   - Publicación por lote de todo un mes, con resumen previo de qué se va a
     publicar y qué actividades del mes anterior quedarán archivadas.
   - Resolución de conflictos entre fuentes: las dos versiones lado a lado, con
     la precedencia sugerida y el motivo, y la decisión final del humano.
   - Bloqueo duro: si una fila tiene errores, el botón de publicar está
     deshabilitado y explica por qué.

5. HISTORIAL — /programacion/historial
   - Versiones por actividad y por lote de importación: quién, cuándo, qué cambió
     (diff campo a campo).
   - Descarga del archivo original de cada importación.
   - Reversión de un lote completo de importación.

6. TRANSVERSAL
   - Componentes shadcn/ui, dark mode, responsive, español de Colombia.
   - Fechas y horas siempre mostradas en America/Bogota, con una etiqueta visible
     que lo diga. En el cliente NUNCA se hace aritmética de zonas horarias: se
     recibe UTC de la API y se formatea.
   - Accesible: foco visible, contraste AA, todas las acciones de arrastrar y
     soltar con una alternativa por teclado y por menú.
   - Estados de carga, vacío y error en TODAS las vistas.
   - Optimistic updates con reversión ante error de la API.
   - Realtime de Supabase para que dos editores simultáneos no se pisen; aviso
     cuando otro usuario está editando la misma actividad.
   - Toda acción destructiva pasa por confirmación y queda en audit_logs.

CRITERIO DE ACEPTACIÓN
Un administrador sube el Excel del mes, corrige las dos filas con advertencia en
pantalla, mueve un taller de fecha arrastrándolo en el calendario, elimina una
actividad cancelada y publica el mes completo — todo sin salir de la interfaz,
sin escribir SQL, y dejando rastro en audit_logs de cada paso.
```

---

## P3 — Adapter de IA y motor de respuesta

```
Lee CLAUDE.md §2, §3.2, §3.5 y §7.

Objetivo: capa de IA desacoplada y un motor de respuesta que NO alucina.

Entrega:
1. infrastructure/ai/: AnthropicAdapter, OpenAIAdapter, GeminiAdapter, todos
   implementando AIProviderPort. Factory por configuración del tenant.
   Reintentos, timeout, manejo de rate limit, y registro en ai_traces
   (tokens, latencia, costo estimado).
2. Cero referencias a un proveedor concreto fuera de infrastructure/ai/.
   Añade un test que lo verifique por análisis de imports.
3. infrastructure/knowledge/HybridRetriever (implementa KnowledgeRetrieverPort):
   - paso 1: filtro SQL duro por tenant_id, venue, rango de fechas, audiencia,
     status='published'
   - paso 2: re-ranking semántico con pgvector sobre los candidatos
   - devuelve como máximo N actividades con su source_url
4. application/conversation/ResponderUseCase: clasifica intención
   (programación | horarios_tarifas | ubicación | reserva | queja | fuera_de_alcance
   | saludo), recupera contexto, construye el prompt y valida la salida.
5. Prompt de sistema del bot, en archivo versionado
   `src/prompts/fundacion_epm/system.md`, que codifique CLAUDE.md §7:
   persona, alcance, prohibiciones, formato WhatsApp (máx ~600 caracteres,
   máx 5 actividades, `*Título* — día, hora · público · lugar`),
   comportamiento ante ausencia de dato y reglas de escalamiento.
6. Guardarraíl anti-alucinación: la respuesta se rechaza y se reintenta con
   instrucción correctiva si menciona una actividad, fecha o precio que no está en
   el contexto recuperado. Si falla dos veces, responde el mensaje de fallback con
   el canal oficial.
7. Suite de evaluación en tests/evals/ con los casos de KB_FUNDACION_EPM.md §6,
   incluyendo los casos negativos (mes sin parrilla, pregunta de facturación de EPM,
   petición de reservar).

Criterio de aceptación: cambiar el proveedor de IA se logra con una variable de
entorno, sin tocar application/ ni domain/; las evals de alucinación pasan al 100 %.
```

---

## P4 — Canal WhatsApp: webhook, envío y Embedded Signup

```
Lee CLAUDE.md §3.4, §3.6, §8. Solo Cloud API oficial de Meta.

Objetivo: canal de WhatsApp productivo y multitenant.

Entrega:
1. GET /api/v1/webhooks/whatsapp: verificación de suscripción (hub.challenge).
2. POST /api/v1/webhooks/whatsapp: verificación HMAC SHA-256 de
   X-Hub-Signature-256 con el APP_SECRET ANTES de parsear; 200 inmediato;
   encolado en Redis; procesamiento en worker.
3. Parser tipado de todos los eventos: messages (text, image, audio, document,
   location, interactive, button), statuses (sent, delivered, read, failed),
   errores. Ignorar con log lo desconocido, nunca reventar.
4. Idempotencia por wamid con SETNX en Redis y restricción única en base de datos.
5. Resolución de tenant por phone_number_id. Si no resuelve: log de seguridad y
   descarte, jamás procesar.
6. infrastructure/messaging/MetaCloudApiClient (implementa MessagingPort):
   enviar texto, plantilla, media, botones interactivos y marcar como leído.
   Backoff ante 429 y ante errores 5xx.
7. Gestión de ventana de 24 h: fuera de ventana solo plantilla aprobada.
8. Embedded Signup: endpoints de OAuth, intercambio de código por token,
   registro del WABA y del número, suscripción de la app al WABA,
   almacenamiento CIFRADO del token con puntero token_ref.
9. Sincronización y consulta de plantillas vía Business Management API.
10. Tests de integración con respx: firma inválida, wamid repetido, tenant
    desconocido, evento de estado, texto entrante feliz, envío fuera de ventana.
11. docs/API.md con OpenAPI y docs/WHATSAPP.md con el flujo de onboarding.

Criterio de aceptación: una firma inválida devuelve 403; un wamid repetido no
genera doble respuesta; ningún token aparece en logs ni en base de datos en claro.
```

---

## P5 — Panel administrativo y bandeja tipo WhatsApp Web

```
Lee CLAUDE.md §2, §6, §7 y docs/API.md.

Nota de alcance: la vista /programacion y la cola de revisión de extracciones se
adelantaron a P2B. Esta fase NO las reimplementa; sí debe integrarlas en la
navegación, las guardas por rol y el sistema de diseño comunes.

Objetivo: frontend Next.js multitenant, en español, con dark mode y responsive.

Entrega:
1. Auth con Supabase, guardas por rol (owner, admin, agente, lector) y selector
   de tenant para superadmin.
2. /inbox estilo WhatsApp Web: panel izquierdo con conversaciones (búsqueda,
   filtros por estado y canal), panel central de mensajes con estados de entrega,
   panel derecho con información del contacto y del espacio consultado.
   Realtime de Supabase para mensajes entrantes. Indicador de ventana de 24 h con
   cuenta regresiva y bloqueo de texto libre cuando expira, ofreciendo plantillas.
3. /venues: CRUD de espacios y de venue_facts, con historial de versiones.
   (Las actividades y su revisión ya viven en /programacion, de P2B.)
4. /dashboard: métricas de conversaciones, intenciones más frecuentes, tasa de
   escalamiento, preguntas sin respuesta (oro para el backlog de datos), costo de IA.
5. /configuracion: canales, plantillas, proveedor de IA, prompts, roles, usuarios.
6. /logs: auditoría y errores con filtros.
7. Componentes shadcn/ui, dark mode, accesible (foco visible, contraste AA,
   navegación por teclado), estados de carga y de error en todas las vistas.

Criterio de aceptación: un agente puede tomar una conversación del bot y responder;
las vistas de P2B quedan integradas en la navegación y respetan las guardas por rol.
```

---

## P6 — Endurecimiento, observabilidad y despliegue

```
Lee CLAUDE.md §8 y docs/SECURITY.md.

Objetivo: dejar la plataforma lista para producción.

Entrega:
1. Rate limiting por tenant y por wa_id en Redis; protección contra bucles de bots.
2. Cifrado en reposo de tokens de Meta y del contenido de mensajes; rotación
   documentada; enmascaramiento de números en todos los logs.
3. Política de retención y job de purga configurable por tenant.
4. Aviso de privacidad automático en el primer contacto y flujo de opt-out
   ("BAJA"/"SALIR") con registro de consentimiento (Ley 1581 de 2012).
5. Observabilidad: logs estructurados con trace_id de punta a punta, métricas
   Prometheus, alertas de webhook fallido, de ingesta sin correr y de tasa de
   fallback alta.
6. Backups automáticos de PostgreSQL y prueba de restauración documentada.
7. GitHub Actions: pipeline completo con entornos staging y producción,
   migraciones automáticas y rollback documentado.
8. Pruebas de carga básicas del webhook y documento de capacidad.
9. Revisión final de documentación: los 11 documentos obligatorios completos,
   coherentes y actualizados, más CLAUDE.md §11 al día.

Criterio de aceptación: checklist de SECURITY.md al 100 %; despliegue a staging
reproducible desde cero siguiendo solo DEPLOYMENT.md.
```

---

## Prompt de mantenimiento mensual (recurrente)

```
Lee CLAUDE.md y KB_FUNDACION_EPM.md.

Tarea mensual de programación:
1. Importa el Excel del mes (fuente primaria) para los espacios que lo hayan
   enviado. Si algún espacio no lo envió, ejecuta la ingesta de respaldo
   (Issuu / web) y déjalo señalado en el reporte.
2. Reporta: actividades nuevas, actualizadas, en conflicto y descartadas.
   En los conflictos, indica qué fuente ganó por precedencia y cuáles quedaron
   pendientes de decisión humana.
3. Revalida los venue_facts contra las páginas oficiales y marca las diferencias.
4. Si una fuente cambió de estructura y el extractor falla, NO improvises un parche:
   documenta el cambio, propón la corrección y espera aprobación. Aplica igual al
   Excel: si el archivo no cumple docs/CONTRATO_EXCEL_PROGRAMACION.md, el
   importador reporta errores por fila, nunca adivina.
5. Actualiza KB_FUNDACION_EPM.md §5 con los vacíos que sigan abiertos y
   CLAUDE.md §11 con el estado.
```

---

## Notas de uso

- **Un prompt, una sesión.** Mezclar P2A y P3 en la misma sesión degrada la calidad y rompe la trazabilidad de los commits.
- **P2B depende de los endpoints de P2A.** Ejecuta P2A completo y con tests en verde antes de empezar P2B. Si quieres ver la interfaz antes, pide en P2A que exponga primero los endpoints de importación y listado, y arranca P2B contra ellos.
- Si Claude Code propone una librería no oficial de WhatsApp, es una violación de `CLAUDE.md` §1: detén la sesión y corrige el contexto.
- Si una respuesta empieza a escribir código antes del plan, recuérdalo con: *"Detente. Presenta el plan y los archivos que vas a tocar antes de escribir código."*
