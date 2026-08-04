# Flujo conversacional del bot (árbol de decisiones)

Especificación del árbol de decisiones por botones del bot de la Fundación
Grupo EPM. Se escribe **antes** de implementarlo (CLAUDE.md §12.2) y es la
fuente de verdad del copy y de la navegación.

## Por qué botones y no solo texto libre

El primer corte de P3 pasa el texto del usuario tal cual como filtro de
búsqueda sobre los títulos de las actividades: no clasifica la intención. Una
pregunta como «¿qué hay esta semana?» no comparte palabras con ningún título y
no encuentra nada.

Un botón **es** una intención exacta. No hay que adivinarla, no interviene el
LLM en la ruta principal, y la consulta a la base es determinista. Es más
rápido, no cuesta tokens y no puede alucinar. El texto libre sigue existiendo
como salida de escape hacia la IA.

## Límites de WhatsApp que condicionan el diseño

| Elemento | Límite |
|---|---|
| Botones de respuesta rápida | **3 por mensaje**, título ≤ 20 caracteres |
| Mensaje de lista | 1 lista, ≤ **10 filas** en total, título de fila ≤ 24 caracteres |
| Descripción de fila | ≤ 72 caracteres |
| Cuerpo del mensaje | ≤ 1024, pero la regla del proyecto es **~600** (CLAUDE.md §7) |

Son 17 espacios (3 principales + 14 UVA), así que **no caben en una sola
lista**. Por eso las UVA se agrupan en una fila que abre su propia lista.

---

## Nivel 0 — Menú principal

Se envía cuando: es el primer mensaje del contacto, o el usuario escribe
`menú` / `menu` / `inicio` / `hola`, o cuando una rama termina.

**Cuerpo** (con el aviso de privacidad **solo en el primer contacto**, según
CLAUDE.md §7):

```
¡Hola! Soy el asistente de la Fundación Grupo EPM 👋

Te puedo ayudar con la programación cultural y los horarios de la
Biblioteca EPM, el Museo del Agua, el Parque de los Deseos y las UVA.

¿Qué necesitás?
```

**Botones:**

| id | Título | Va a |
|---|---|---|
| `menu_programacion` | `Ver programación` | Nivel A |
| `menu_horarios` | `Horarios y lugares` | Nivel B |
| `menu_humano` | `Hablar con alguien` | Nivel C |

---

## Rama A — Ver programación

### A.1 Elegir espacio (mensaje de lista)

**Cuerpo:** `¿De cuál espacio querés ver la programación?`
**Botón de la lista:** `Elegir espacio`

| id | Fila | Descripción |
|---|---|---|
| `ven_biblioteca-epm` | `Biblioteca EPM` | Centro, La Alpujarra |
| `ven_museo-del-agua` | `Museo del Agua` | Parque de los Pies Descalzos |
| `ven_parque-de-los-deseos` | `Parque de los Deseos` | Casa de la Música, Carabobo |
| `ven_uva_lista` | `Ver las UVA` | 14 espacios en los barrios |
| `prog_todas` | `Todo lo de esta semana` | Sin importar el espacio |

### A.2 Lista de UVA (si eligió `ven_uva_lista`)

Son 14 y el límite es 10 filas, así que van en dos páginas de 7, con una fila
final `Ver más UVA` en la primera.

Página 1: La Armonía · El Encanto · Ilusión Verde · Aguas Claras ·
La Cordialidad · La Alegría · La Esperanza · **Ver más UVA**

Página 2: La Imaginación · Los Guayacanes · Mirador S. Cristóbal ·
Nuevo Amanecer · San Fernando · Los Sueños · La Libertad

> `UVA Mirador de San Cristóbal` tiene 28 caracteres y el límite de la fila es
> 24: se abrevia a `UVA Mirador S. Cristóbal`. El nombre completo se usa en el
> cuerpo de la respuesta, no en la fila.

### A.3 Respuesta con la programación

Consulta determinista: `activities` del espacio elegido, `status = published`,
`deleted_at IS NULL`, `starts_at >= hoy`, ordenadas por fecha, **límite 5**.

**Si hay resultados** (formato de CLAUDE.md §7):

```
📅 *Biblioteca EPM* — próximas actividades

*Club de lectura infantil* — jue 7 ago, 3:00 p.m. · infantil · Sala 3
*Taller de robótica* — sáb 9 ago, 10:00 a.m. · juvenil · Sala de Formación
...

¿Querés ver más o consultar otro espacio?
```

**Si NO hay resultados** — esto es lo importante: hay que distinguir dos casos
distintos (el puerto ya expone `has_programming_for` justamente para esto):

- **No hay parrilla cargada para el mes:**
  ```
  Todavía no tengo cargada la programación de agosto para la Biblioteca EPM.
  La podés consultar en bibliotecaepm.com o al 4442400.
  ```
- **Hay parrilla pero nada más adelante:** decirlo así, y ofrecer el mes
  siguiente.

Nunca rellenar con conocimiento propio (CLAUDE.md §1.5).

**Botones:** `Ver más` (`prog_mas`) · `Otro espacio` (`menu_programacion`) ·
`Menú` (`menu_inicio`)

---

## Rama B — Horarios y lugares

### B.1 Elegir espacio

Misma lista que A.1, con ids `fact_<slug>`.

### B.2 Respuesta con los datos del espacio

Consulta a `venue_facts` del espacio (vigentes hoy) más los campos de
`venues`: dirección, barrio, teléfonos, correos.

```
📍 *Museo del Agua EPM*

🕐 Horario: mar a vie 9:00 a.m.–5:00 p.m. · sáb, dom y festivos 10:00 a.m.–6:00 p.m.
🎟️ Entrada: $8.000 · gratis para menores de 4 años
📌 Carrera 57 #42-139, Parque de los Pies Descalzos
📞 3808300

¿Necesitás algo más?
```

Cada dato sale de un `venue_fact` real. **Un dato que no está en la base no se
menciona** — no se escribe «horario por confirmar» inventando la estructura,
simplemente no aparece esa línea. Los espacios cuyo horario está marcado como
pendiente en `KB_FUNDACION_EPM.md` §5 (Biblioteca general, las UVA) no tienen
esa línea y hay que decirlo explícitamente:

```
Todavía no tengo confirmado el horario de la UVA La Armonía.
Te lo pueden confirmar en el 4442400.
```

**Botones:** `Cómo llegar` (`fact_mapa_<slug>`, solo si el espacio tiene
coordenadas) · `Otro espacio` (`menu_horarios`) · `Menú` (`menu_inicio`)

---

## Rama C — Hablar con alguien

Marca la conversación como `escalated` y responde:

```
Claro. Le paso tu consulta a una persona del equipo de la Fundación.

Contame en un mensaje qué necesitás y en qué horario te podemos contactar,
y alguien te responde por este mismo chat en horario de oficina
(lunes a viernes, 8:00 a.m. a 5:00 p.m.).
```

Sin botones: se espera texto libre, que queda guardado para que un humano lo
lea en el inbox.

---

## Comodines — valen en cualquier punto del árbol

| Entrada del usuario | Qué hace |
|---|---|
| `menú`, `menu`, `inicio`, `hola`, `buenas` | Vuelve al Nivel 0 |
| `queja`, `pqrsdf`, `reclamo`, `hablar con una persona`, `asesor` | Rama C directo |
| `BAJA`, `SALIR`, `ELIMINAR MIS DATOS` | Opt-out: marca `opt_out_at`, confirma y **deja de responder** (Ley 1581 de 2012) |
| Cualquier otro texto libre | Ruta de IA: recupera contexto de la base y responde solo con eso. Al final, ofrece el menú |

## Reglas transversales

1. **El aviso de privacidad va una sola vez**, en el primer contacto, y se
   registra en `contacts.consent_at`. No se repite en cada mensaje.
2. **Fuera de la ventana de 24 h no se envía texto libre ni botones**, solo
   plantillas aprobadas (CLAUDE.md §3.6). El árbol solo aplica dentro de la
   ventana.
3. **Todo lo que el bot dice sale de la base de datos.** Si el dato no está,
   lo dice y entrega el canal oficial del espacio.
4. **Solo actividades `published`.** Un borrador nunca llega al público
   (ADR 005). Hoy las 50 actividades de julio siguen en `draft`: hasta que se
   publiquen, la Rama A responderá «no tengo cargada la programación», que es
   el comportamiento correcto, no un error.

## Pendiente para implementarlo

- `MessagingPort` necesita `send_list` (hoy tiene `send_interactive`, que solo
  cubre los 3 botones).
- `parse_webhook` debe extraer las respuestas de botón y de lista
  (`interactive.button_reply.id` y `interactive.list_reply.id`); hoy solo lee
  mensajes de tipo `text`.
- Una máquina de estados por conversación para saber en qué nodo está cada
  contacto.
