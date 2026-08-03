# CONTRATO_EXCEL_PROGRAMACION.md

> Derivado del archivo real `Programacion_Formativa_Biblioteca_Julio_2026.xlsx` (Biblioteca EPM, julio 2026), analizado el 2026-08-03.
> Este documento es el **contrato de entrada** del importador. Si el archivo del mes no lo cumple, el importador falla con errores por fila, **nunca adivina**.

---

## 1. Estructura del libro

- **N hojas**, una por segmento de público. En la muestra: `Programación infantil` y `Jóvenes y adultos`.
- El nombre de la hoja **NO es un identificador estable**. Se usa como pista de `audience`, pero la hoja se reconoce por sus **encabezados**, no por su nombre.
- **Fila 1:** título de la hoja, combinado. Formato observado: `Programación infantil – Julio 2026`. Contiene **mes y año**, y es la única fuente del año en todo el libro.
- **Fila 2:** encabezados.
- **Fila 3 en adelante:** datos, una fila por curso.
- Se ignoran hojas sin los encabezados esperados (con aviso, no con error fatal).

### Detección de la fila de encabezados
No asumir que siempre es la fila 2. Escanear las primeras 10 filas y elegir la que contenga al menos 6 de los encabezados canónicos, normalizando: minúsculas, sin tildes, sin espacios extremos, colapsando espacios internos.

---

## 2. Columnas canónicas

| Encabezado en el archivo | Campo destino | Obligatorio | Notas |
|---|---|---|---|
| `Título del curso` | `title` | Sí | Si está vacío, la fila se descarta con error |
| `Descripción` | `description` | No | Texto largo, tal cual |
| `Día(s)` | `weekdays_raw` | No | Redundante con `Fecha(s)`; se usa solo para **validación cruzada** |
| `Fecha(s)` | `dates_raw` | Sí | Texto libre. Ver §3 |
| `Horario` | `time_raw` | Sí | Ver §4 |
| `Lugar` | `room_raw` | No | Ver §5 |
| `Público` | `audience_raw` | No | Ver §6 |
| `Inscripción` | `registration_raw` | No | Ver §7 |
| `Enlace de inscripción` | `registration_url` | No | URL. Ver §7 |

**Sinónimos aceptados** (normalizados): `Título` / `Título del curso` / `Actividad` / `Nombre`; `Fecha` / `Fecha(s)` / `Fechas`; `Hora` / `Horario`; `Lugar` / `Espacio` / `Sala`; `Público` / `Público objetivo` / `Dirigido a`.

Columna desconocida ⇒ se conserva en `extra` y se reporta, no se descarta el archivo.

---

## 3. `Fecha(s)` — el campo difícil

Sin año. El año y el mes de referencia salen del título de la fila 1; si no se puede parsear, se toman del parámetro `--month` de la carga y se marca `confidence` reducido.

Patrones observados y requeridos:

| Entrada real | Interpretación |
|---|---|
| `01 de julio` | 1 ocurrencia |
| `07 y 14 de julio` | 2 ocurrencias |
| `14, 21 y 28 de julio` | 3 ocurrencias |
| `02, 09, 16 y 23 de julio` | 4 ocurrencias |
| `Todos los martes de julio` | Recurrencia semanal → expandir a los martes del mes |
| `Del 23 de junio al 9 de julio` | Rango **que cruza mes** |

**Reglas:**
1. Una fila con N fechas genera **N filas en `activities`**, agrupadas por `activity_group_id` para poder editarlas o borrarlas en bloque desde el panel.
2. Un rango (`Del X al Y`) con `Día(s)` presente se expande solo a los días de semana indicados (`Martes y jueves` ⇒ martes y jueves dentro del rango).
3. Fecha fuera del mes de la carga ⇒ **no se descarta**: se importa y se marca `out_of_month_warning`. El caso `Del 23 de junio al 9 de julio` es legítimo.
4. Fecha imposible (31 de febrero) ⇒ error de fila, no del archivo.
5. Todo se resuelve en `America/Bogota` y se **persiste en UTC**.

---

## 4. `Horario`

Formato observado: `2:00 p.m. a 4:00 p.m.`, `10:00 a.m. a 12:00 m.`, `1:30 p.m. a 3:30 p.m.`, `2:30 p.m. a 4:30 p.m.`

**Reglas:**
- `m.` = mediodía = **12:00**. `12:00 a.m.` = medianoche. Este es el error clásico: no mapear `12:00 m.` a `00:00`.
- Se aceptan `p.m.`, `pm`, `P.M.`, `p. m.` (con espacio duro incluido).
- Separadores: `a`, `-`, `–`, `hasta`.
- `ends_at` anterior a `starts_at` ⇒ error de fila.
- Sin hora de fin ⇒ `ends_at = null`. **Prohibido** asumir dos horas de duración.

---

## 5. `Lugar`

Valores observados: `Taller Infantil`, `Taller infantil`, `Sala de formación`, `Sala de Formación`, `Sala de Formación 3`, `Sala de formación 4`, `Sala de Investigadores`, `Cafetería`, `No especificado en el documento`.

**Reglas:**
- Normalizar (minúsculas, sin tildes) y resolver contra un **catálogo de salas** por espacio (tabla `rooms`).
- `Sala de Formación` y `Sala de Formación 3` **no son la misma sala**: el número es significativo. Sin número ⇒ sala genérica.
- Coincidencia difusa por encima del 0.85 ⇒ se asigna con `confidence` reducido y se marca para revisión. Por debajo ⇒ se deja `room_raw` y se pide resolución manual en el panel.
- Centinelas que se convierten en `null`: `No especificado en el documento`, `No especificado`, `N/A`, `-`, `Por definir`, `Pendiente`.
- Sala nueva no catalogada ⇒ el panel ofrece crearla; **no se crea automáticamente**.

---

## 6. `Público`

Valores observados: `Niñas y niños de 4 a 7 años`, `Niñas y niños de 7 a 10 años`, `Niñas y niños de 2 a 4 años`, `Niños y niñas de 9 años en adelante`, `Niñas y niños de 6 a 11 años`, `Jóvenes y adultos`.

Se extrae a tres campos:
- `audience` (enum): `infantil | juvenil | adulto | familiar | todo_publico`
- `age_min`, `age_max` (enteros, nullable). `de 9 años en adelante` ⇒ `age_min=9, age_max=null`.
- `audience_raw` se conserva siempre para mostrarlo textualmente al usuario del bot.

Si la celda está vacía, se usa el nombre de la hoja como pista y se marca `confidence` bajo. **Nunca** se inventa un rango de edad.

---

## 7. `Inscripción` y `Enlace de inscripción`

Valores observados en `Inscripción`: `No requiere inscripción` o **vacío**. En `Enlace de inscripción`: URLs de Microsoft Forms, algunas con cadenas de consulta muy largas.

**Tabla de decisión:**

| `Inscripción` | Enlace | `requires_registration` |
|---|---|---|
| `No requiere inscripción` | vacío | `false` |
| `No requiere inscripción` | presente | `false` + advertencia de inconsistencia |
| vacío | presente | `true` |
| vacío | vacío | `null` → **requiere resolución humana**, no se asume nada |
| `Requiere inscripción` / `Con inscripción` / `Cupo limitado` | cualquiera | `true` |

La URL se valida (esquema http/https, host resoluble sintácticamente) pero **no se acorta ni se reescribe**.

---

## 8. Metadatos que NO están en el archivo

Se capturan en el formulario de carga del panel, nunca se infieren:

- `tenant_id` — de la sesión
- `venue_slug` — el espacio (Biblioteca EPM, Museo del Agua, una UVA concreta…). El nombre del archivo es una pista que se **propone**, no se aplica
- `month` — se propone desde el título de la fila 1 y se **confirma** el operador
- `price` — no existe columna de precio; queda `null` salvo que el operador lo indique

---

## 9. Salida del importador

Por cada fila se produce un `ActivityExtraction` con:

```
title, description, venue_slug, room_id | room_raw, starts_at (UTC), ends_at (UTC),
recurrence, audience, age_min, age_max, audience_raw, price,
requires_registration, registration_url, confidence, evidence_snippet,
source_id, source_row (hoja + número de fila), activity_group_id, warnings[]
```

`evidence_snippet` para una fuente Excel es la **fila original serializada**, para que el revisor vea exactamente qué se interpretó.

Todo entra con `status='draft'`. Ninguna fila con `errors` no vacíos puede publicarse.

---

## 10. Plantilla oficial

El panel debe ofrecer la **descarga de una plantilla `.xlsx`** generada desde este contrato, con los encabezados canónicos, una hoja por público, una fila de ejemplo y validación de datos en las columnas de enum. Enviar a los equipos esta plantilla reduce la mayoría de los casos difíciles de arriba.
