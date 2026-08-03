# DATABASE.md

> Esquema, índices y política de aislamiento multitenant. Las reglas que lo gobiernan están en [`CLAUDE.md`](../CLAUDE.md) §1.2, §4 y §8.

## 1. Dónde vive

PostgreSQL 17 gestionado por **Supabase** (ADR 003). Extensiones: `pgcrypto` (ya venía instalada; da `gen_random_uuid()`) y `pgvector` 0.8 (la instala la migración inicial; habilita el re-ranking semántico de ADR 006). Ambas en el esquema `extensions`, que Supabase ya tiene en el `search_path`.

### Conectarse: usa el pooler, no la conexión directa

`db.<ref>.supabase.co` solo publica registro **AAAA (IPv6)**. En cualquier red o plataforma sin IPv6 —incluida Railway— falla con un error de resolución que no sugiere la causa. Usa el **Session pooler**:

```
host:    aws-1-<región>.pooler.supabase.com
puerto:  5432
usuario: <rol>.<project-ref>        ← ojo: no es solo el nombre del rol
```

**Percent-encodea los caracteres especiales de la contraseña** en la URL. Un `+` literal se interpreta como espacio al parsear y la autenticación falla con un mensaje de credenciales inválidas: escríbelo `%2B`. Igual con `@` (`%40`), `:` (`%3A`), `/` (`%2F`) y `#` (`%23`).

## 2. Dos identidades de conexión, y por qué

Esta es la decisión menos obvia del diseño, así que conviene entender el problema antes que la solución.

En PostgreSQL, **RLS no se aplica en dos casos**: a roles con `BYPASSRLS`, y al **dueño de la tabla** (salvo que se active `FORCE ROW LEVEL SECURITY`). En Supabase:

```
postgres        BYPASSRLS = true     ← con este rol corren las migraciones
service_role    BYPASSRLS = true
anon            BYPASSRLS = false
```

Si el backend se conectara como `postgres` —lo natural, porque es la credencial que da Supabase—, **las políticas de RLS no se aplicarían nunca**. El aislamiento dependería solo del filtro de la aplicación, y el test de aislamiento pasaría en falso: no estaría probando nada.

Por eso hay dos identidades:

| | Rol | `BYPASSRLS` | Para qué |
|---|---|---|---|
| **Runtime** | `epm_app` | ❌ no | Todas las consultas del backend |
| **Migraciones** | `postgres` | ✅ sí | `alembic upgrade/downgrade` y el seed |

`epm_app` lo crea la migración inicial: tiene `LOGIN NOBYPASSRLS`, recibe `SELECT/INSERT/UPDATE/DELETE` sobre `public` y **no recibe `CREATE`**, así que no puede alterar el esquema. No es dueño de ninguna tabla. Además, todas las tablas llevan `FORCE ROW LEVEL SECURITY`, de modo que la política aplica incluso al dueño.

Variables de entorno correspondientes:

- `DATABASE_URL` → `epm_app` (runtime)
- `DATABASE_MIGRATION_URL` → `postgres` (DDL)
- `APP_DB_PASSWORD` → la contraseña con la que la migración crea `epm_app`; debe coincidir con la de `DATABASE_URL`

El seed también usa la conexión de migraciones, y no por comodidad: el seed **crea** el tenant, y las políticas impiden ver o insertar filas de un tenant que todavía no está en contexto. Es el problema del huevo y la gallina; por eso es una tarea de administración, no de runtime.

## 3. Cómo funciona el aislamiento

Cada tabla con `tenant_id` tiene una política idéntica:

```sql
CREATE POLICY tenant_isolation ON <tabla>
    USING      (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
```

Tres detalles deliberados:

- **`USING` filtra la lectura, `WITH CHECK` la escritura.** Sin `WITH CHECK`, un tenant podría *insertar* filas a nombre de otro aunque no pudiera leerlas.
- **El `true` de `current_setting`** hace que devuelva `NULL` en vez de error cuando la variable no está puesta. Comparar contra `NULL` no devuelve nada: **sin tenant en contexto no se ve ninguna fila**. Ese es el fallo seguro — olvidarse de fijar el tenant devuelve cero resultados, nunca los de todos.
- **`NULLIF(..., '')`** evita que una cadena vacía reviente el cast a `uuid`.

`tenants` es la única excepción: su política compara contra `id`, no contra `tenant_id`.

### Fijar el tenant: `SET LOCAL`, nunca `SET`

```python
async with tenant_session(tenant_id) as session:
    ...  # todo lo de dentro ve solo ese tenant
```

Internamente emite `set_config('app.tenant_id', <uuid>, true)`, que es un `SET LOCAL`: **vive solo hasta el final de la transacción**.

Esto no es un detalle de estilo. Con `SET` a secas el ajuste quedaría pegado a la conexión, y al devolverla al pool **la siguiente petición heredaría el tenant de la anterior** — una fuga de datos entre clientes, intermitente y muy difícil de diagnosticar. Hay un test dedicado a comprobar que no se filtra entre transacciones.

## 4. Tablas

16 tablas de negocio. Todas menos `tenants` llevan `tenant_id` con `ON DELETE CASCADE`: borrar un tenant se lleva todo lo suyo, que es el comportamiento que exige una petición de supresión bajo la Ley 1581.

```
identity        tenants · users
channels        whatsapp_accounts · templates
conversations   contacts · conversations · messages
knowledge       venues · rooms · venue_facts · activities · activity_embeddings
ingestion       sources · ingestion_runs
observabilidad  ai_traces · audit_logs
```

Notas sobre algunas:

- **`rooms`** — catálogo de salas por espacio (contrato de Excel §5). El número es significativo: «Sala de Formación» y «Sala de Formación 3» son filas distintas. `normalized_name` (minúsculas, sin tildes) es contra lo que el importador hace la coincidencia difusa. Una sala desconocida **no se crea automáticamente**.
- **`activities`** — una fila de Excel con N fechas produce N actividades unidas por `activity_group_id`, para editarlas o borrarlas en bloque. `deleted_at` implementa el soft delete con papelera de 30 días de P2B. `evidence_snippet` guarda el fragmento original (la fila serializada, en el caso del Excel) que el revisor ve al lado del JSON estructurado.
- **`activity_embeddings`** — lleva `tenant_id` propio aunque sea derivable de la actividad. Sin él no se le puede aplicar RLS, y una tabla sin RLS es una fuga.
- **`whatsapp_accounts`** — `token_ref` es un **puntero al secreto cifrado, nunca el token**.

## 5. Índices

`tenant_id` es la **primera columna de todo índice compuesto**. No es cosmético: es lo que permite a PostgreSQL descartar de entrada las filas de otros tenants, y el filtro de tenant está presente en el 100 % de las consultas.

Los tres que cargan el peso:

| Índice | Para qué |
|---|---|
| `ix_activities_tenant_id_venue_id_starts_at` | Consulta principal del bot: tenant + espacio + rango de fechas (ADR 006) |
| `uq_messages_tenant_id_wamid` | Idempotencia de webhooks |
| `uq_activities_dedupe` | Deduplicación del pipeline de ingesta |

**Los dos últimos son parciales**, y ahí está la sutileza:

```sql
-- Un mensaje saliente en cola aún no tiene wamid. Si el índice no fuera
-- parcial, varios NULL colisionarían entre sí.
uq_messages_tenant_id_wamid    WHERE wamid IS NOT NULL

-- Una actividad borrada no debe impedir volver a cargar la misma.
uq_activities_dedupe           WHERE deleted_at IS NULL
```

El índice único de `messages` es lo que respalda en base de datos al `SETNX` de Redis: si el worker se cae entre ambos, la restricción sigue impidiendo la doble respuesta.

`whatsapp_accounts.phone_number_id` es único **global**, no por tenant: un número solo puede pertenecer a un tenant. Eso es lo que hace segura la resolución de tenant en el webhook.

## 6. Restricciones que duplican al dominio

Tres `CHECK` en `activities` repiten invariantes que la entidad ya valida:

```sql
ck_activities_ends_after_starts   ends_at IS NULL OR ends_at >= starts_at
ck_activities_age_range           age_max IS NULL OR age_min IS NULL OR age_max >= age_min
ck_activities_confidence_range    confidence BETWEEN 0 AND 1
```

La duplicación es intencional: la validación del dominio protege del error de programación, la de la base protege de la carga manual por SQL y de cualquier ruta que no pase por la aplicación.

## 7. Migraciones

```bash
cd backend
alembic upgrade head       # aplicar
alembic downgrade base     # revertir por completo
alembic current            # revisión actual
```

Toda migración lleva `upgrade` y `downgrade` **reales y probados** (CLAUDE.md §1.8). El de la inicial se verificó de punta a punta: `upgrade head` → `downgrade base` → `upgrade head`.

`downgrade` elimina las 16 tablas y el rol `epm_app`, pero **no borra las extensiones**, por dos motivos distintos: `pgcrypto` ya existía y no le corresponde a esta migración destruirla; `vector` sí la creó, pero borrarla afecta a un esquema compartido y dejarla es inocuo — no ocupa nada sin columnas que la usen, y el `upgrade` es idempotente gracias al `IF NOT EXISTS`.

## 8. Seed

```bash
cd backend
python -m src.infrastructure.database.seed fundacion-epm
```

Carga desde [`data/seeds/fundacion-epm/`](../data/seeds/fundacion-epm/): el tenant, los 17 espacios (Museo del Agua + Biblioteca EPM + Parque de los Deseos + 14 UVA) y sus `venue_facts`. Es **idempotente**: se puede ejecutar las veces que haga falta y converge al contenido de los YAML.

Dos reglas que el cargador impone y que fallan la carga si se incumplen:

1. **Todo hecho lleva `source_url`.** Un dato sin fuente no entra a la base.
2. **Los datos marcados «Pendiente» en `KB_FUNDACION_EPM.md` §5 se omiten, no se inventan.** En concreto no existen: el horario general de la Biblioteca EPM (solo se conoce el de préstamo), los horarios de las 14 UVA, ni el correo público del Parque de los Deseos. El bot debe decir que no tiene el dato y dar el canal oficial, no rellenarlo.

Las 4 UVA operadas por el INDER tampoco están: el bot no responde por ellas.

## 9. Verificar que el aislamiento funciona

```bash
cd backend
pytest tests/integration/test_multitenant_isolation.py -v
```

Ocho comprobaciones, y la primera es la que da sentido a las demás: **que el rol de runtime no omita RLS**. Si esa falla, el resto son decorativas.

Las otras siete: un tenant ve solo lo suyo; sin contexto no se ve nada; no se puede escribir en otro tenant; el contexto no se filtra entre transacciones; el rol de migraciones sí lo ve todo (contraprueba, para que el test no pase por tener las tablas vacías); todas las tablas tienen RLS activado **y forzado**; y todas tienen su política.

Las dos últimas recorren `TENANT_SCOPED_TABLES` en [`models/base.py`](../backend/src/infrastructure/database/models/base.py): añadir una tabla con `tenant_id` y olvidar su política hace fallar el build.
