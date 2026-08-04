"""Registro del número de WhatsApp de un tenant.

El webhook resuelve el tenant a partir del `phone_number_id` que Meta envía
(CLAUDE.md §1.6). Esa traducción sale de `whatsapp_accounts`: sin una fila
ahí, un mensaje entrante no se puede atribuir a nadie y se descarta.

Mientras no exista el Embedded Signup (P4), el registro se hace a mano con
`python -m src.cli register-channel`.
"""

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from src.config.settings import get_settings


@dataclass(frozen=True)
class ChannelRegistration:
    tenant_slug: str
    phone_number_id: str
    waba_id: str
    display_number: str
    created: bool

    def render(self) -> str:
        verbo = "Registrado" if self.created else "Actualizado"
        return (
            f"{verbo} el número {self.display_number} "
            f"(phone_number_id {self.phone_number_id}) "
            f"para el tenant {self.tenant_slug}."
        )


async def register_channel(
    *,
    tenant_slug: str,
    phone_number_id: str | None = None,
    waba_id: str | None = None,
    display_number: str = "",
) -> ChannelRegistration:
    """Crea o actualiza la cuenta de WhatsApp de un tenant.

    Los identificadores caen por omisión a los de la configuración, para que el
    caso normal sea un comando sin argumentos.

    Va por la conexión de administración: escribir en `whatsapp_accounts` con
    RLS activo exigiría fijar antes el tenant, y aquí lo estamos estableciendo.

    Nota sobre `token_ref`: la columna guarda un **puntero** al secreto, nunca
    el token (CLAUDE.md §4). Hoy apunta a la variable de entorno; cuando exista
    el cifrado en reposo apuntará a la entrada correspondiente.
    """
    settings = get_settings()
    phone_number_id = phone_number_id or settings.meta_phone_number_id
    waba_id = waba_id or settings.meta_waba_id

    if not phone_number_id or not waba_id:
        raise ValueError(
            "Faltan META_PHONE_NUMBER_ID y META_WABA_ID en la configuración, "
            "y no se pasaron por argumento."
        )

    engine = create_async_engine(settings.migration_url)
    try:
        async with engine.begin() as conn:
            tenant_id = await conn.scalar(
                text("SELECT id FROM tenants WHERE slug = :slug"),
                {"slug": tenant_slug},
            )
            if tenant_id is None:
                raise ValueError(
                    f"El tenant '{tenant_slug}' no existe. ¿Falta cargar el seed?"
                )

            existing = await conn.scalar(
                text(
                    "SELECT id FROM whatsapp_accounts"
                    " WHERE phone_number_id = :pid AND tenant_id = :tenant_id"
                ),
                {"pid": phone_number_id, "tenant_id": tenant_id},
            )

            if existing is None:
                await conn.execute(
                    text(
                        "INSERT INTO whatsapp_accounts"
                        " (tenant_id, waba_id, phone_number_id, display_number,"
                        "  token_ref, status)"
                        " VALUES (:tenant_id, :waba_id, :pid, :display,"
                        "         'env:META_ACCESS_TOKEN', 'active')"
                    ),
                    {
                        "tenant_id": tenant_id,
                        "waba_id": waba_id,
                        "pid": phone_number_id,
                        "display": display_number or phone_number_id,
                    },
                )
            else:
                await conn.execute(
                    text(
                        "UPDATE whatsapp_accounts"
                        " SET waba_id = :waba_id, status = 'active'"
                        " WHERE id = :id"
                    ),
                    {"waba_id": waba_id, "id": existing},
                )
    finally:
        await engine.dispose()

    return ChannelRegistration(
        tenant_slug=tenant_slug,
        phone_number_id=phone_number_id,
        waba_id=waba_id,
        display_number=display_number or phone_number_id,
        created=existing is None,
    )
