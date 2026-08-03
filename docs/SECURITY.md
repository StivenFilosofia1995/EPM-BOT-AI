# SECURITY.md

> Las reglas de seguridad obligatorias están en [`CLAUDE.md`](../CLAUDE.md) §8. Este documento explica cómo se implementan y qué falta.

## 1. Reporte de vulnerabilidades

Si encuentras una vulnerabilidad, **no abras un issue público**. Escribe al responsable técnico del proyecto con: descripción, pasos de reproducción, impacto estimado y, si la tienes, una propuesta de corrección.

## 2. Gestión de secretos

- **Ningún secreto en el repositorio.** Solo [`.env.example`](../.env.example), documentado y con todos los valores vacíos.
- `.env` está en `.gitignore`. Si alguna vez se commitea uno por accidente: rotar **todas** las credenciales afectadas antes de reescribir la historia; asumir que quedaron expuestas.
- `VERIFY_TOKEN` de Meta: aleatorio de **≥32 bytes** y **distinto por entorno** (`openssl rand -hex 32`).
- `APP_SECRET_KEY`: mínimo 16 caracteres, validado por `Settings`. En producción, generarlo aleatorio.
- Los tokens de larga duración de Meta se **cifran en reposo** (envelope encryption). La base de datos guarda un puntero `token_ref`, nunca el token; la clave maestra vive en `TOKEN_ENCRYPTION_KEY` (variable de entorno, fuera de la base de datos).

## 3. Webhooks de Meta

1. Verificación **HMAC SHA-256** de la cabecera `X-Hub-Signature-256` contra `META_APP_SECRET`, **antes de parsear el cuerpo**. Firma inválida ⇒ **403 sin filtrar información** sobre por qué falló.
2. Comparación de firmas en **tiempo constante** (`hmac.compare_digest`).
3. Idempotencia por `wamid`: `SETNX` en Redis más restricción única en base de datos. Un reintento de Meta no produce doble respuesta.
4. El `tenant_id` se resuelve desde el `phone_number_id` del evento. **Si no resuelve: log de seguridad y descarte.** Nunca se procesa ni se responde.

## 4. Multitenancy

El aislamiento es de **defensa en profundidad**, en dos capas:

- **Aplicación:** toda tabla de negocio lleva `tenant_id`; toda consulta lo filtra. Ningún método de repositorio existe sin `tenant_id`.
- **Base de datos:** RLS activo en todas las tablas con `tenant_id`. Aunque la aplicación tenga un bug, la base no devuelve filas de otro tenant.

`SUPABASE_SERVICE_ROLE_KEY` **omite RLS**: solo en el backend, jamás en el frontend ni en variables `NEXT_PUBLIC_*`. El frontend usa exclusivamente la clave `anon`.

## 5. Rate limiting

Por `tenant_id` y por `wa_id` en Redis (`WEBHOOK_RATE_LIMIT_PER_MINUTE`). Protege contra abuso y contra bucles entre bots.

## 6. Cabeceras de seguridad y límites (nginx)

Configurado en [`infra/nginx/conf.d/default.conf`](../infra/nginx/conf.d/default.conf):

| Cabecera | Valor | Para qué |
|---|---|---|
| `X-Content-Type-Options` | `nosniff` | Evita que el navegador adivine el tipo MIME |
| `X-Frame-Options` | `DENY` | Anti clickjacking |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | No filtrar rutas internas a terceros |
| `Permissions-Policy` | cámara, micrófono y geolocalización deshabilitados | Reduce superficie de APIs del navegador |
| `Content-Security-Policy` | `default-src 'self'`, `frame-ancestors 'none'` | Mitiga XSS e inyección de recursos |

`server_tokens off` oculta la versión de nginx. `client_max_body_size 10m` limita el cuerpo de la petición: los webhooks de Meta son pequeños, el margen es para cargas de archivos del panel.

**Pendiente para producción:** `Strict-Transport-Security` (requiere TLS terminado; la línea está comentada en la config) y HTTPS obligatorio con redirección desde HTTP.

La CSP incluye `'unsafe-inline'` y `'unsafe-eval'` en `script-src` porque Next.js los necesita en desarrollo. **Endurecer con nonces antes de producción.**

## 7. Logs y datos personales

- **Sin PII en claro.** Números enmascarados (`57******1234`).
- El contenido de los mensajes va en tabla cifrada, con retención definida.
- Ningún token, clave ni firma aparece en logs.
- Cada petición lleva un `request_id` propagado de nginx al backend y devuelto en la respuesta y en la envoltura de error como `trace_id`: permite investigar un incidente sin registrar el contenido.

## 8. Protección de datos (Ley 1581 de 2012, Colombia)

- **Minimización:** solo se guarda lo necesario para responder.
- **Retención definida** y job de purga configurable por tenant.
- **Aviso de privacidad** en el primer mensaje de cada contacto nuevo, con la finalidad del tratamiento y el enlace a la política.
- **Canal de supresión / opt-out** (`BAJA` / `SALIR`) con registro de consentimiento.

**Bloqueante de negocio abierto:** falta designar formalmente al responsable del tratamiento de datos y obtener la autorización de uso de marca y datos de la Fundación. Ver `CLAUDE.md` §11 y `KB_FUNDACION_EPM.md` §5.

## 9. Dependencias

CI ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)) corre en cada push y PR:

- **`pip-audit`** sobre el backend (`--skip-editable`: el propio paquete no está publicado en PyPI). Bloqueante.
- **`npm audit`** sobre el frontend. **Bloqueante en `critical`**, informativo en `high`.

### Por qué `npm audit` no bloquea en `high`

El scaffold de Next.js 16.2.12 (última versión publicada) arrastra tres advisories `high` transitivos en `postcss` y `sharp`. `npm audit fix --force` "resuelve" proponiendo `next@9.3.3`, un downgrade de siete versiones mayores — peor remedio que la enfermedad. No hay versión corregida upstream.

Decisión: bloquear en `critical` y dejar `high` como paso informativo visible en el log de CI. **Revisar en cada actualización de Next.js** y volver a `high` bloqueante en cuanto exista una release que lo resuelva.

Además: Dependabot activo para actualizaciones de seguridad.

## 10. Contenedores

- Imágenes **multi-stage**: el toolchain de build no llega a la imagen final.
- Ambos servicios corren con **usuario sin privilegios** (`app` en el backend, `nextjs` en el frontend), nunca como root.
- **Solo nginx publica puertos al host.** Backend, frontend y Redis viven en la red interna del compose.
- Healthchecks en los cuatro servicios; `nginx` espera a que backend y frontend estén *healthy*, no solo arrancados.

## 11. Checklist previa a producción

- [ ] HTTPS obligatorio con redirección desde HTTP
- [ ] `Strict-Transport-Security` activo
- [ ] CSP endurecida (eliminar `unsafe-inline` / `unsafe-eval` con nonces)
- [ ] `CORS_ORIGINS` restringido a los dominios reales
- [ ] Secretos generados aleatoriamente y distintos por entorno
- [ ] RLS verificado con un test que use el rol no privilegiado
- [ ] Rotación de tokens de Meta documentada y probada
- [ ] Retención y purga configuradas por tenant
- [ ] Aviso de privacidad y flujo de opt-out en producción
- [ ] Responsable del tratamiento de datos designado
- [ ] Backups automáticos de PostgreSQL **con restauración probada**
- [ ] Enmascaramiento de números verificado en todos los logs
