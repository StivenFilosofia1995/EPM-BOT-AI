# API

Base: `/api/v1`. Todas las respuestas son JSON.

Estado actual: solo existen las rutas del panel de programación (P2B). El
webhook de WhatsApp y las rutas de conversación llegan en P4.

---

## 1. Autenticación (temporal)

Todas las rutas de `/api/v1` exigen la cabecera `X-Admin-Token`, comparada
contra la variable de entorno `ADMIN_API_TOKEN`.

| Situación | Respuesta |
|---|---|
| Cabecera ausente o token distinto | `401` |
| `ADMIN_API_TOKEN` sin configurar en el servidor | `503` |

El 503 es deliberado: sin token configurado las rutas se apagan en vez de
quedar abiertas. Un despliegue al que se le olvidó la variable no debe servir
datos a cualquiera.

> ⚠️ **Esto no es autenticación.** Un token compartido no identifica a nadie,
> no tiene roles y no permite saber quién hizo qué. Se elimina en P5, cuando
> entre la autenticación de Supabase. Mientras siga aquí, no expongas el panel
> públicamente.

El frontend nunca envía esta cabecera desde el navegador: llama a
`/api/backend/*`, un proxy de Next.js que la añade en el servidor. Si el token
viajara al cliente estaría en el bundle de JavaScript.

### Tenant

Se resuelve en el servidor desde `DEFAULT_TENANT_SLUG`; el cliente no lo envía
ni puede cambiarlo. Toda consulta corre dentro de `tenant_session()`, con el
rol `epm_app` y RLS activo. En P5 el tenant saldrá del usuario autenticado.

---

## 2. Formato de error

```json
{
  "error": {
    "code": "http_422",
    "message": "El mes debe tener el formato AAAA-MM, no 'julio'",
    "details": null,
    "trace_id": "64766a60-7f7f-4bd4-a5ec-9d719ac7d983"
  }
}
```

En errores de validación de esquema, `details` trae la lista de FastAPI con el
campo y el motivo. El panel muestra ese texto tal cual: casi siempre dice
exactamente qué falló.

---

## 3. Rutas

### `GET /venues`

Espacios del tenant, ordenados por tipo y nombre.

```json
[{ "slug": "biblioteca-epm", "name": "Biblioteca EPM", "kind": "biblioteca" }]
```

---

### `GET /activities`

Listado paginado de actividades.

| Parámetro | Tipo | Por omisión | Notas |
|---|---|---|---|
| `venue` | string | — | slug del espacio |
| `month` | string | — | `AAAA-MM`. `422` si no cumple el formato o el mes está fuera de 1–12 |
| `status` | string | — | `draft`, `published`, `archived` |
| `only_warnings` | bool | `false` | solo actividades con advertencias del importador |
| `search` | string | — | busca en título y descripción |
| `limit` | int | `50` | 1–200 |
| `offset` | int | `0` | ≥ 0 |

**El filtro de mes se resuelve en hora de Bogotá**, no en UTC: preguntar por
julio debe devolver lo que el operador ve como julio. Una actividad del 1 de
julio a las 8 a.m. en Medellín es 13:00 UTC del mismo día, pero una del 31 de
julio a las 9 p.m. es 02:00 UTC del 1 de agosto — filtrando en UTC se
perdería.

Respuesta:

```json
{ "items": [ /* … */ ], "total": 50, "limit": 50, "offset": 0 }
```

Cada actividad trae, entre otros campos: `title`, `description`, `venue_slug`,
`room_name`, `room_raw`, `starts_at`, `ends_at`, `audience`, `audience_raw`,
`age_min`, `age_max`, `requires_registration`, `registration_url`, `status`,
`confidence`, `warnings`, `source_row`, `evidence_snippet`.

`starts_at` y `ends_at` van **en UTC**. El cliente los formatea a
`America/Bogota`; no se envían pre-formateados para que no existan dos
verdades sobre la hora. Los campos que el Excel no traía van a `null` — nunca
se rellenan con un valor plausible.

`room_raw`, `audience_raw`, `source_row` y `evidence_snippet` conservan lo que
decía el archivo, para que el revisor pueda comparar lo interpretado con el
original.

---

### `POST /programacion/import/preview`

Sube un Excel, lo parsea y devuelve qué se interpretó. **No escribe nada** en
la base de datos.

`multipart/form-data`:

| Campo | Tipo | Obligatorio |
|---|---|---|
| `file` | archivo `.xlsx` o `.xlsm`, ≤ 10 MB | sí |
| `venue` | slug del espacio | sí |
| `month` | `AAAA-MM` | sí |

Rechazos:

| Código | Motivo |
|---|---|
| `415` | La extensión no es `.xlsx` ni `.xlsm` |
| `413` | El archivo supera 10 MB |
| `400` | El archivo está vacío |
| `422` | `month` mal formado, o el archivo no se pudo leer como Excel |

Se comprueba la extensión y el **tamaño ya leído**, no el `content-type` ni la
cabecera `content-length`: ambos los controla el cliente.

Respuesta:

```json
{
  "summary": {
    "file_name": "Programacion_Formativa Biblioteca_Julio_2026.xlsx",
    "venue_slug": "biblioteca-epm",
    "rows_read": 23,
    "rows_ok": 22,
    "rows_warning": 1,
    "rows_error": 0,
    "activities": 50,
    "unknown_columns": [],
    "sheets_skipped": []
  },
  "rows": [
    {
      "sheet": "Programación infantil",
      "row_number": 3,
      "status": "ok",
      "title": "¡A Jugar!",
      "dates_raw": "01 de julio",
      "time_raw": "2:00 p.m. a 4:00 p.m.",
      "room_raw": "Taller Infantil",
      "audience_raw": "Niñas y niños de 4 a 7 años",
      "activities": 1,
      "warnings": [],
      "errors": [],
      "starts_at": ["2026-07-01T19:00:00Z"]
    }
  ]
}
```

`rows_read` cuenta **filas del Excel**; `activities` cuenta actividades tras
expandir fechas. Una fila que dice «todos los martes» produce una actividad por
martes: por eso 23 filas dan 50 actividades. Los campos `*_raw` son el texto
literal de la celda.

`status` por fila es el semáforo del panel: `ok`, `warning`, `error`.

---

### `POST /programacion/import`

Igual que la vista previa, más un campo opcional:

| Campo | Tipo | Por omisión |
|---|---|---|
| `force` | bool | `false` |

Persiste el resultado. **Todo entra como `draft`.** Publicar es un acto humano
aparte (ADR 005); esta ruta no lo hace nunca.

```json
{
  "summary": { /* igual que en la vista previa */ },
  "ingestion_run_id": "ea4e0d0f-a861-4ac1-a712-bf117cf41e31",
  "activities_inserted": 0,
  "activities_updated": 50,
  "skipped_unchanged": false,
  "message": "0 actividades nuevas y 50 actualizadas, todas en borrador."
}
```

**Idempotencia.** Se guarda el hash del contenido del archivo. Volver a subir
el mismo archivo devuelve `skipped_unchanged: true`, con el resumen en ceros y
sin tocar la base. `force=true` reprocesa igualmente: hace *upsert*, no inserta
duplicados. Verificado con el archivo real — reimportar deja el total en 50.

Cada importación queda registrada en `ingestion_runs`, incluida la que se
saltó.

---

## 4. `/health`

Fuera de `/api/v1` y sin token, para los healthchecks de Docker y Railway.

```json
{ "status": "ok" }
```

---

## 5. Cabeceras

Toda respuesta lleva `X-Request-Id`. Si la petición trae una, se conserva; si
no, se genera. Es el mismo valor que aparece en los logs y en el `trace_id` de
los errores.
