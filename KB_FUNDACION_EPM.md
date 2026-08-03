# KB_FUNDACION_EPM.md — Base de conocimiento semilla (Tenant: Fundación Grupo EPM)

> **Estado:** semilla verificada por scraping manual el **2026-08-03**.
> **Uso:** este documento es la fuente para el *seed* inicial de la base de datos (`tenants`, `venues`, `venue_facts`, `sources`). NO es la fuente en tiempo de ejecución: el bot responde desde PostgreSQL, no desde este archivo.
> **Regla de oro:** todo dato aquí lleva `fuente` + `verificado_en`. Un dato sin fuente no entra a la base de datos.

---

## 1. Hallazgos de la investigación de fuentes (crítico para la arquitectura)

| # | Hallazgo | Implicación arquitectónica |
|---|---|---|
| H1 | **No existe API pública ni feed (RSS/iCal/JSON-LD) de programación.** El portal es Adobe AEM renderizado en servidor. | Se requiere pipeline de ingesta propio. Prohibido depender de un endpoint inexistente. |
| H2 | La página oficial de programación (`/fundacion-grupo-epm/programacion/`) publica **solo 3 destacados por espacio**, no la parrilla completa. | El scraping de esa página sirve como *señal de cambio*, no como fuente completa. |
| H3 | El **3 de agosto de 2026 esa página aún mostraba actividades de julio** (e incluso una fecha de junio en "Costurero literario"). | La fuente web es **poco confiable en frescura**. Obligatorio: campo `confidence`, `valid_from/valid_to` y respuesta honesta del bot cuando el mes vigente no está cargado. |
| H4 | La **parrilla completa mensual se publica como revista PDF en Issuu**, cuenta `issuu.com/bibliotecaepm1`, un documento por espacio y por mes (ej.: `/docs/programacion_museodelagua_-_abril`, `/docs/uva_programaci_n_abril`, `/docs/parquedeseos_-_programacio_n_-_abril`, `/docs/programacion_formativa_mayo_-_bepm`). | Ingesta de respaldo: **PDF → extracción → estructuración con LLM → revisión humana → publicación**. Los slugs no son deterministas: se descubren desde los enlaces "Ver toda la programación". ⚠️ **Superado por H8 como fuente primaria.** |
| H5 | Los PDFs son piezas **maquetadas por diseño** (texto en capas, a veces rasterizado). | El extractor debe soportar `pdfplumber` (texto) **y** fallback a rasterizado + visión multimodal. |
| H6 | Los datos **estables** (horarios, tarifas, direcciones, teléfonos) sí están bien publicados en las páginas de cada espacio. | Se cargan como `venue_facts` versionados, con revalidación mensual. |
| H7 | Reservas del Museo del Agua se hacen por **Google Forms** externo; el Concurso Nacional de Cuento tiene su propia convocatoria. | El bot **entrega el enlace**, nunca simula la reserva. Alcance cerrado explícitamente. |
| H8 | **La Fundación produce la parrilla mensual en un Excel interno** (una hoja por segmento de público, encabezados estables), del que se derivan el PDF de Issuu y la web. Es estructurado, autoritativo y llega antes que cualquier publicación. Ver `docs/CONTRATO_EXCEL_PROGRAMACION.md`. | **Corrige H4 como supuesto de fuente primaria.** El Excel pasa a ser la fuente principal e Issuu queda como respaldo. El importador de Excel es **determinista y no usa LLM**. Ver ADR 009. |

**Conclusión de diseño:** el bot NO debe hacer scraping en el camino caliente de la conversación. Responde contra una base curada; la ingesta es un proceso asíncrono, versionado y con aprobación humana (`draft → review → published`). La fuente primaria es el Excel interno (H8); las publicadas (H4) son respaldo y verificación.

---

## 2. Entidad y ámbito

- **Nombre legal / marca actual:** Fundación Grupo EPM (antes "Fundación EPM"). Filial del Grupo EPM, sin ánimo de lucro, creada el 10 de agosto de 2000.
- **Ecosistema de Experiencias Sostenibles:** 17 espacios de ciudad.
- **Teléfono corporativo:** +57 604 448 69 60
- **Correo:** contactenos@fundacionepm.org.co
- **Oficinas:** Carrera 58 # 42-125, piso 3, Medellín. Lunes a viernes 7:30 a.m. – 5:30 p.m.
- **Línea anticorrupción / ética:** 01 8000 522 955
- **PQRSDF:** formulario en `saia-fundacionepm.netsaia.com/ws/pqr/index.html`
- **Fuente:** https://www.grupo-epm.com/fundacion-grupo-epm/ — verificado 2026-08-03

---

## 3. Espacios (tabla `venues`)

### 3.1 Museo del Agua EPM
| Campo | Valor |
|---|---|
| `slug` | `museo-del-agua` |
| Dirección | Carrera 57 # 42-139, Parque de los Pies Descalzos, Medellín |
| Teléfonos | (604) 380 1790 · (604) 381 1790 · +57 300 276 1391 |
| Oferta educativa | (604) 380 3082 · +57 300 815 0898 |
| Correo | museodelaguaepm@fundacionepm.org.co (histórico: museodelagua@fundacionepm.org.co) |
| Horario | Martes a viernes desde 8:30 a.m., cierre de taquilla y último ingreso 3:30 p.m. Sábados, domingos y festivos desde 9:30 a.m., último ingreso 4:00 p.m. |
| Cierre | El primer día hábil de la semana no abre, por mantenimiento |
| Duración recorrido | ~2 horas |
| Aforo | Ingresos por grupos de máximo 16 personas cada 15 minutos; grupos > 16 requieren reserva previa |
| Tarifa residentes Colombia | $8.000 COP |
| Tarifa extranjeros | $12.000 COP |
| Gratuidades | Menores de 4 años; mayores de 60 años; instituciones educativas oficiales de estratos 1, 2 y 3; docentes con carné o carta institucional |
| Beneficio estratos 1-2-3 | Con factura EPM original y vigente en taquilla, ingresan 3 personas gratis |
| "Museo para todas y todos" | Último sábado del mes, ingreso gratuito hasta agotar aforo |
| Reservas | Google Forms (enlace en la página de horarios y tarifas) |
| Salas | 9 salas en 3 ejes: Evolución del planeta · Agua recurso vital · Ecosistemas · Culturas forjadas por el agua · Abastecimiento de agua · Transformación del ambiente · Derechos y distribución del recurso hídrico · Planeta azul · Aula-Taller |
| Programas | Club de Amigos (8-12 años), semillero juvenil (14-26 años), Club de Antaño (adultos mayores), rutas pedagógicas para docentes |
| Fuente | `/que-hacemos/programas/museo-del-agua/` y `/horarios-y-tarifas/` — verificado 2026-08-03 |

### 3.2 Biblioteca EPM
| Campo | Valor |
|---|---|
| `slug` | `biblioteca-epm` |
| Dirección | Carrera 54 No. 44-48, Plaza de Cisneros (La Alpujarra), Medellín |
| Teléfono | (604) 380 7516 |
| Correo | bibliotecaepm@epm.com.co |
| Préstamo y devolución | Lunes a sábado, 8:00 a.m. – 5:30 p.m. |
| Entrada | Libre, todos los públicos |
| Especialización | Ciencia, Industria, Medio Ambiente y Tecnología |
| Hitos | Inaugurada el 2 de junio de 2005. Premio RUSA (American Library Association) por AccessBot |
| Convocatoria vigente | XIV Concurso Nacional de Cuento — tema "Viajes que cuentan historias". Del 25 de junio al 30 de agosto de 2026 (o hasta 400 propuestas). Categorías: infantil 7-13, juvenil 14-19, adultos 20+. Cuentos inéditos en español, 500-1.500 palabras. Premios: 3 portátiles (primeros lugares) y 3 bonos de librería de $500.000 (segundos lugares) |
| ⚠️ Pendiente | **Horario general de la sede no confirmado en la web** (solo el de préstamo). Confirmar con el equipo antes de publicar. |
| Fuente | `/que-hacemos/programas/biblioteca-epm/`, boletín de prensa 2026 — verificado 2026-08-03 |

### 3.3 Parque de los Deseos y Casa de la Música
| Campo | Valor |
|---|---|
| `slug` | `parque-de-los-deseos` |
| Dirección | Calle 71 # 52-30, barrio Sevilla, Medellín (junto a estación Universidad del Metro) |
| Teléfonos | (604) 516 6005 · +57 300 278 3221 · +57 300 548 5853 |
| Correo de programación | maria.alvarez@fundacionepm.org.co (⚠️ correo personal: preferir el corporativo en respuestas del bot) |
| Casa de la Música | Martes a domingo, 8:00 a.m. – 9:00 p.m., incluyendo festivos |
| Servicios | Salas de ensayo gratuitas, recorridos guiados, talleres, conciertos, exposiciones |
| Líneas | Cine Accesible (audiodescripción y LSC), MUROCK, Medellín Music Lab, Feria de los Deseos, Mercados Sostenibles EPM, Huerta de los Deseos (agroecología) |
| Fuente | `/que-hacemos/programas/parque-de-los-deseos-y-casa-de-la-musica/` — verificado 2026-08-03 |

### 3.4 UVA — Unidades de Vida Articulada
14 UVA operadas por la Fundación Grupo EPM (13 de EPM + 1 de Aguas Nacionales). Existen 18 construidas; 4 son de la Alcaldía y las opera el INDER (**el bot no responde por esas**).

| UVA | Barrio / Municipio | Dirección | Teléfono |
|---|---|---|---|
| La Armonía | Santa Inés, Medellín | Cra 36 # 84-98 | 301 250 0814 |
| El Encanto | Santander, Medellín | Cra 76 # 104D-01 | 300 610 1643 |
| Ilusión Verde | Los Naranjos, Medellín | Cl 3B Sur # 29B-56 | 301 262 0802 |
| Aguas Claras | Navarra, Bello | Diagonal 50A AV 20-251 | 300 698 5313 / 304 216 1826 |
| La Cordialidad | Santo Domingo Savio 1, Medellín | Cra 42B # 110A-04 | 300 742 6086 |
| La Alegría | Santa Inés, Medellín | Cra 41 # 79-66 | 304 352 6729 |
| La Esperanza | San Pablo, Medellín | Cl 96 # 34-100 | 300 546 6882 |
| La Imaginación | San Miguel, Medellín | Cra 40 # 61-04 | 301 249 8942 |
| Los Guayacanes | Cucaracho, Medellín | Cl 65C # 94-04 | 300 749 7082 |
| Mirador de San Cristóbal | Corregimiento San Cristóbal | Cra 131 # 66-20 | 301 681 6877 |
| Nuevo Amanecer | La Avanzada, Medellín | Cl 107B # 23A-138 | 304 351 2877 |
| San Fernando | San Fernando, Itagüí | Cra 47 # 85-256 | 301 247 6351 |
| Los Sueños | Versalles 1, Medellín | Cra 28 # 69-04 | 301 250 0814 |
| La Libertad | La Libertad, Medellín | Cl 57 # 17B-50 | 304 351 2880 |

Nota: la UVA La Armonía alberga el **Museo de la Central Hidroeléctrica Piedras Blancas**.
⚠️ **Pendiente:** horarios de atención por UVA no publicados en la web. Solicitar al equipo operativo.
Fuente: `/que-hacemos/programas/uva/` — verificado 2026-08-03

---

## 4. Fuentes de ingesta (tabla `sources`)

| id | tipo | url | frecuencia | confiabilidad |
|---|---|---|---|---|
| `excel-admin` | `xlsx` | archivo interno de la Fundación, cargado por el panel (ver H8) | mensual | **máxima (fuente primaria y autoritativa)** |
| `manual` | `human` | carga directa del equipo de comunicaciones vía panel | evento | muy alta (corrección puntual) |
| `issuu-uva` | `pdf_issuu` | descubierta desde el enlace "Ver toda la programación" (pestaña UVA) | mensual | alta (respaldo y verificación) |
| `issuu-parque` | `pdf_issuu` | ídem, pestaña Parque de los Deseos | mensual | alta (respaldo) |
| `issuu-biblioteca` | `pdf_issuu` | ídem, pestaña Biblioteca EPM | mensual | alta (respaldo) |
| `issuu-museo` | `pdf_issuu` | ídem, pestaña Museo del Agua | mensual | alta (respaldo) |
| `venue-pages` | `html` | páginas de cada espacio (horarios, tarifas, contacto) | mensual | alta |
| `noticias` | `html` | https://www.grupo-epm.com/fundacion-grupo-epm/noticias/ | semanal | alta |
| `web-programacion` | `html` | https://www.grupo-epm.com/fundacion-grupo-epm/programacion/ | diaria | media (desactualizada, ver H3) |

**Precedencia en conflicto:** `excel-admin` > `manual` > `issuu-*` > `venue-pages` > `web-programacion`.

Cuando dos fuentes discrepan **se conservan ambas versiones** y la resuelve un humano en el panel: una discrepancia entre el Excel y lo publicado suele ser un cambio real de última hora, no un error de extracción. Ver ADR 009.

---

## 5. Vacíos conocidos (backlog de datos)

1. Horario general de la Biblioteca EPM (no solo préstamo).
2. Horarios de atención de cada UVA.
3. Calendario de cierres por festivos y mantenimiento (Museo: "primer día hábil de la semana" es ambiguo cuando el lunes es festivo — **requiere regla explícita del negocio**).
4. Aforo y política de inscripción por actividad (varias piden "requiere inscripción" sin decir cómo).
5. Confirmar el correo de contacto público del Parque de los Deseos (evitar exponer correo personal).
6. Autorización formal de la Fundación para usar la marca y los datos en un canal de WhatsApp, y designación del responsable de tratamiento de datos (Ley 1581 de 2012, Colombia).

---

## 6. Ejemplos de intención → respuesta (para evals)

| Pregunta del usuario | Fuente de la respuesta | Comportamiento esperado |
|---|---|---|
| "¿Cuánto cuesta entrar al Museo del Agua?" | `venue_facts` | Dato exacto + gratuidades + aclaración de que puede cambiar |
| "¿Qué hay este sábado en el Parque de los Deseos?" | `activities` filtradas por fecha y `venue` | Máx. 5 actividades, con hora y público objetivo |
| "¿Qué hacen los niños en la UVA La Imaginación?" | `activities` + `venues` | Filtrar por `audience=familiar/infantil` |
| "Quiero reservar para 30 estudiantes" | `venue_facts` + escalamiento | Entregar enlace/teléfono. **No** prometer reserva |
| "¿Está abierto el lunes?" | `venue_facts` | Explicar el cierre por mantenimiento |
| "¿Cuándo cierra el concurso de cuento?" | `activities` (convocatoria) | 30 de agosto de 2026, 11:59 p.m., o hasta 400 propuestas |
| "¿Cuánto cuesta la factura de mi casa?" | — | Fuera de alcance: derivar a EPM (la Fundación no es EPM) |
| Pregunta sobre un mes sin parrilla cargada | — | Decir honestamente que aún no está publicada + enlace oficial |
