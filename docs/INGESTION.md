# INGESTION.md

> Pipeline que convierte las fuentes de la Fundación en filas de `activities` publicables. Las decisiones que lo gobiernan están en [ADR 009](./adr/009-excel-como-fuente-primaria.md) y `CLAUDE.md` §3.5.

## 1. Estado

| Fuente | Tipo | Estado |
|---|---|---|
| **Excel administrativo** | `excel_admin` | ✅ implementada |
| Página oficial de programación | `web_programacion` | ⬜ pendiente |
| PDF de Issuu | `pdf_issuu` | ⬜ pendiente |
| Páginas de cada espacio | `venue_page` | ⬜ pendiente |

El Excel se implementó primero por una razón concreta: es la **fuente primaria** y la única **determinista**. No pasa por el LLM, así que se puede probar exhaustivamente contra el archivo real. Las demás necesitan visión, rasterizado y scraping, y son de respaldo.

## 2. Flujo

```
descubrir → obtener → extraer → estructurar → validar → draft → revisión → publicar
                                                          │        │
                                                          │        └── panel (P2B), humano
                                                          └── aquí termina la ingesta
```

**Nada llega a `published` desde el pipeline.** El importador deja todo en `draft`; publicar es un acto humano en el panel (ADR 005). Es la protección contra que un error de parseo se convierta en algo que el bot le repite mil veces a la gente por WhatsApp.

Para el Excel, «estructurar» no existe como paso: el archivo ya viene estructurado. Ahí está la ventaja de la fuente primaria.

## 3. Precedencia entre fuentes

```
excel_admin > manual > pdf_issuu > venue_page > web_programacion
```

Cuando dos fuentes discrepan **se conservan ambas versiones** y decide una persona en el panel. Una discrepancia entre el Excel y lo publicado suele ser un cambio real de última hora, no un error de extracción: descartar la versión perdedora borraría esa señal.

## 4. Importar un Excel

```bash
cd backend
python -m src.cli ingest \
    --tenant fundacion-epm \
    --source excel \
    --file "../Programacion_Formativa Biblioteca_Julio_2026.xlsx" \
    --venue biblioteca-epm \
    --month 2026-07
```

`--venue` y `--month` no están en el archivo y los aporta el operador (contrato §8). El mes solo se usa **si no se puede leer del título de la fila 1**; cuando hay que recurrir a él, la fila se marca con `month_from_parameter` y confianza reducida.

Salida real sobre el archivo de julio de 2026:

```
23 filas leídas · 22 correctas · 1 con advertencia · 0 con error
50 actividades tras expandir fechas
guardadas: 50 nuevas, 0 actualizadas (todas en draft)
```

**23 son filas, no actividades.** Una fila con N fechas produce N actividades unidas por `activity_group_id`, para poder editarlas o borrarlas en bloque desde el panel.

### Reimportar

Es idempotente por dos caminos independientes:

- **Por hash.** Si el contenido del archivo es idéntico a una corrida anterior con éxito, no se reprocesa. Se salta con `--force`.
- **Por clave.** Con `--force`, las actividades existentes se actualizan en vez de duplicarse. La clave es `(tenant, espacio, título normalizado, inicio)`, la misma del índice único de deduplicación.

Una actividad que ya fue **publicada no se toca**: el `UPDATE` filtra por `status = 'draft'`. Una reimportación no puede devolver a borrador algo que alguien ya revisó y aprobó.

## 5. Las trampas del formato

El contrato completo está en [`CONTRATO_EXCEL_PROGRAMACION.md`](./CONTRATO_EXCEL_PROGRAMACION.md). Estas son las que más cuestan y por qué existen:

**`12:00 m.` es mediodía, no medianoche.** En español de Colombia `m.` abrevia *meridiem*. Confundirlo con `a.m.` desplaza la actividad doce horas y el bot da una hora falsa. `12:00 a.m.` sí es medianoche.

**La fila de encabezados no siempre es la 2.** Se escanean las 10 primeras y se acepta la que traiga al menos 6 encabezados canónicos. El archivo lo produce un equipo humano cada mes: una fila en blanco de más no puede romper la importación.

**La hoja se reconoce por sus encabezados, nunca por su nombre.** Renombrar una hoja es lo más fácil del mundo y no debería costar una carga fallida. El nombre solo se usa como pista para el público.

**El número de sala es significativo.** «Sala de Formación» y «Sala de Formación 3» son sitios distintos. Sus nombres se parecen más del 85 %, así que la coincidencia difusa las fundiría; hay una comprobación explícita de número que lo impide.

**Una sala desconocida no se crea sola.** Queda en `room_raw` con advertencia y la resuelve una persona. Crear salas automáticamente llenaría el catálogo de erratas.

**Una fecha fuera del mes no se descarta.** «Del 23 de junio al 9 de julio» en una carga de julio es legítimo. Se importa y se marca `out_of_month` — **solo en las actividades que realmente caen fuera**, no en toda la fila.

**Sin hora de fin, `ends_at` queda nulo.** Está prohibido asumir dos horas de duración.

**Inscripción sin resolver se queda sin resolver.** Celda vacía y sin enlace ⇒ `requires_registration = null`. Prometerle a alguien que puede llegar sin inscribirse cuando no lo sabemos es peor que admitir que no lo sabemos.

**Un error de fila nunca aborta el archivo.** Cada fila se procesa aislada; el operador ve qué entró, qué entró con advertencia y qué no entró y por qué.

## 6. Advertencias

Son un enum, no texto libre, para que el panel pueda filtrar y contar por tipo:

| Advertencia | Significa |
|---|---|
| `out_of_month` | La fecha cae fuera del mes cargado. Se importa igual. |
| `room_unknown` | La sala no está en el catálogo. |
| `room_fuzzy_match` | Se resolvió por parecido; conviene mirarla. |
| `registration_unresolved` | No se pudo determinar si requiere inscripción. |
| `registration_inconsistent` | Dice que no requiere pero trae enlace. |
| `registro_no_es_url` | La columna de enlace trae texto que no es una URL. |
| `audience_from_sheet_name` | El público salió del nombre de la hoja, no de la fila. |
| `month_from_parameter` | El mes salió del parámetro, no del título. |
| `no_end_time` | Sin hora de fin. |
| `unknown_columns` | El archivo trae columnas fuera del contrato. |
| `weekday_mismatch` | El día declarado no coincide con el que cae la fecha. |

## 7. Cuando el Excel cambia de formato

**No improvises un parche.** Si el extractor falla porque el archivo cambió, documenta el cambio, propón la corrección y espera aprobación.

Diagnóstico por síntoma:

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| «hojas ignoradas» con hojas que sí son de programación | Encabezados renombrados | Añadir el sinónimo a `CANONICAL_HEADERS` en [`headers.py`](../backend/src/infrastructure/ingestion/excel/headers.py) |
| Muchas filas con error de fechas | Formato de fecha nuevo | Añadir el patrón a [`dates.py`](../backend/src/infrastructure/ingestion/excel/dates.py) **con su test** |
| Muchas `room_unknown` | Salas nuevas o renombradas | Actualizar `data/seeds/fundacion-epm/rooms.yaml` y recargar el seed |
| `month_from_parameter` en todas | Cambió el título de la fila 1 | Revisar `parse_month_year` |
| Columnas desconocidas | El equipo añadió una columna | Decidir si se mapea a un campo canónico o se deja en `extra` |

Los tests de [`test_excel_parsers.py`](../backend/tests/unit/test_excel_parsers.py) y [`test_excel_source.py`](../backend/tests/unit/test_excel_source.py) usan los valores **observados en el archivo real**. Si fallan tras un cambio, lo que se rompió es la interpretación de la parrilla, y eso llega directo a lo que el bot le dice a la gente.

## 8. Catálogo de salas

Sin catálogo, el importador no puede resolver el campo `Lugar` y deja todas las filas sin sala.

```bash
cd backend && python -m src.cli seed --tenant fundacion-epm
```

Las salas de Biblioteca EPM están en [`data/seeds/fundacion-epm/rooms.yaml`](../data/seeds/fundacion-epm/rooms.yaml) y salen de los valores observados en el archivo real (contrato §5). Los demás espacios aún no tienen catálogo: sus importaciones dejarán `room_raw` sin resolver hasta que se defina.

## 9. Reprocesar un mes ya publicado

1. Ejecuta la importación con `--force`. Las actividades **en draft** se actualizan; las publicadas no se tocan.
2. Para rehacer también las publicadas, hay que despublicarlas primero desde el panel (P2B). Es deliberado: una reimportación no puede alterar por la espalda lo que alguien ya aprobó.
3. Cada corrida queda en `ingestion_runs` con su hash, sus contadores y sus estadísticas, así que siempre se puede auditar qué entró y cuándo.

## 10. Qué falta

Las tres fuentes de respaldo, el estructurador con LLM para PDF y HTML, la resolución de conflictos entre fuentes (necesita más de una) y la tarea programada mensual. Ver `PROMPTS_CLAUDE_CODE.md` → P2A.
