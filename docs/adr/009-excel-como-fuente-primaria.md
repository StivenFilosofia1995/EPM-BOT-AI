# ADR 009 — El Excel interno es la fuente primaria de programación

- **Fecha:** 2026-08-03
- **Estado:** aceptado
- **Revisa a:** ADR 005 (ingesta asíncrona con revisión humana) — no lo deroga, lo acota

## Contexto

El ADR 005 y `CLAUDE.md` §3.5 se escribieron a partir de la investigación de fuentes documentada en `KB_FUNDACION_EPM.md` §1, que solo miró lo **publicado**: no hay API ni feed (H1), la página oficial muestra apenas 3 destacados por espacio (H2) y llegó a estar un mes desactualizada (H3), y la parrilla completa aparece como revista PDF maquetada en Issuu (H4, H5). De ahí salió la conclusión de que Issuu era la fuente autoritativa y que todo debía pasar por extracción de PDF y estructuración con LLM.

Esa investigación no alcanzó a ver lo que ocurre **aguas arriba**. El equipo de la Fundación produce la parrilla mensual en un archivo Excel interno, con una hoja por segmento de público y encabezados estables. El análisis del archivo real (`Programacion_Formativa_Biblioteca_Julio_2026.xlsx`) está en `docs/CONTRATO_EXCEL_PROGRAMACION.md`.

Ese archivo tiene tres propiedades que ninguna fuente publicada tiene:

1. **Es estructurado.** Filas y columnas con encabezados canónicos, no texto maquetado sobre una pieza de diseño.
2. **Es autoritativo.** Es el original del que se derivan el PDF de Issuu y la web, no una representación de él.
3. **Llega antes.** Existe semanas antes de que se publique nada.

El PDF de Issuu es, en realidad, una versión posterior, maquetada y con pérdida de estructura del mismo dato.

## Decisión

**1. El Excel interno pasa a ser la fuente primaria.** Issuu, la página oficial de programación y las páginas de cada espacio quedan como fuentes de **respaldo y verificación**: sirven cuando el Excel no llega a tiempo, y para contrastar que lo publicado coincide con lo cargado.

**2. Nueva precedencia en conflicto:**

```
excel_admin > manual > issuu > venue-pages > web-programacion
```

`manual` (carga directa del equipo de comunicaciones por el panel) queda por debajo de `excel_admin` porque el Excel es el proceso normal y controlado; la carga manual es la excepción puntual. Una corrección hecha a mano sobre una actividad concreta sigue ganando frente a las fuentes publicadas.

**3. El Excel no pasa por el LLM.** El importador es determinista: `openpyxl` más los parsers especificados en el contrato (fechas en español, horarios, salas, público, inscripción). La estructuración con LLM se reserva para las fuentes no estructuradas — PDF y HTML.

**4. Lo que no cambia.** Todo lo extraído entra como `draft` y solo un humano publica. Sigue sin haber scraping en el camino caliente de la conversación. El ADR 005 sigue vigente en su parte esencial: la ingesta es asíncrona, versionada y con revisión humana obligatoria.

## Razones

**Por qué el Excel primero.** Convertir un dato estructurado en PDF maquetado y luego intentar reconstruirlo con visión artificial es perder información a propósito para después pagar por recuperarla, con menos fidelidad y más tarde. Si el original está disponible, se usa el original.

**Por qué el Excel no pasa por el LLM.** Un LLM aporta cuando hay que imponer estructura sobre texto libre. Sobre una celda que ya dice `2:00 p.m. a 4:00 p.m.` no aporta nada y sí introduce riesgo: variabilidad entre corridas, coste, latencia y la posibilidad de que reinterprete un valor correcto. Es la fuente autoritativa; su lectura tiene que ser reproducible y auditable línea por línea. Los casos difíciles del contrato (`12:00 m.` es mediodía, `Sala de Formación` ≠ `Sala de Formación 3`, `Del 23 de junio al 9 de julio` cruza mes) son reglas explícitas y testeables, no juicio.

**Por qué conservar ambas versiones en conflicto.** La precedencia automática resuelve el caso común, pero una discrepancia entre el Excel y lo publicado suele ser señal de un cambio real de última hora, no de un error de extracción. Descartar la versión perdedora borraría la evidencia de esa señal. Se guardan las dos y decide un humano en el panel.

## Consecuencias

**Positivas**

- Mayor fidelidad del dato y coste de IA sustancialmente menor en la ruta principal.
- El importador de Excel es determinista: se puede probar exhaustivamente contra los casos del contrato, sin evals probabilísticas.
- La programación puede cargarse antes de que se publique en Issuu.
- El extractor de PDF deja de ser crítico: si Issuu cambia de maquetación, se degrada una fuente de respaldo, no la principal.

**Negativas y riesgos**

- **Dependencia de un proceso humano.** Si el equipo no envía el Excel, o cambia su formato sin avisar, la fuente primaria falla. Mitigación: las fuentes publicadas siguen implementadas como respaldo, el panel ofrece una plantilla oficial descargable generada desde el contrato, y el importador falla con errores por fila en vez de adivinar.
- **El contrato del Excel es ahora una interfaz crítica.** Un cambio de formato aguas arriba rompe la ingesta. Mitigación: detección de encabezados por contenido y no por posición ni por nombre de hoja, columnas desconocidas conservadas en `extra`, y reporte por fila que nunca aborta el archivo completo.
- **Trabajo adicional en `sources`:** hay que añadir el tipo `excel_admin`, y `ingestion_runs` debe guardar el archivo original en Supabase Storage con su versión, para poder auditar y reprocesar.

## Alternativas descartadas

- **Mantener Issuu como primaria y el Excel como respaldo.** Invierte la calidad de las fuentes: usa la derivada en lugar del original.
- **Pasar también el Excel por el LLM "por consistencia".** Un único camino de código es más simple, pero al precio de volver no determinista la fuente autoritativa. La consistencia se logra en el destino: ambas rutas producen el mismo `ActivityExtraction` (§9 del contrato).
- **Pedir a la Fundación una API o un feed.** Fuera del control del proyecto y sin plazo realista. No descarta retomarlo si algún día existe.

## Referencias

- `docs/CONTRATO_EXCEL_PROGRAMACION.md` — contrato de entrada del importador
- `KB_FUNDACION_EPM.md` §1 (hallazgos H1–H7) y §4 (tabla de fuentes)
- `CLAUDE.md` §3.5 — estrategia de conocimiento
- ADR 005 — ingesta asíncrona con revisión humana
