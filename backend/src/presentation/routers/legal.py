"""Páginas públicas exigidas por Meta para dar de alta la app de WhatsApp
Business: política de privacidad y eliminación de datos de usuario.

Fuera de `/api/v1` a propósito: son páginas para humanos y para el
verificador de Meta, no parte del contrato de API versionado.

**Contenido en borrador** (CLAUDE.md §11: "Responsable del tratamiento de
datos designado" sigue pendiente). Sirve para completar el alta de la app
sin bloquear el proceso, pero el contacto de contacto_privacidad debe
confirmarlo quien la Fundación designe como responsable del tratamiento
antes de tratarlo como definitivo.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["legal"])

_RAZON_SOCIAL = "Fundación Grupo Empresas Públicas de Medellín (Fundación Grupo EPM)"
_NIT = "811024803-3"
_CONTACTO_PROVISIONAL = "notificacionesjudiciales@fundacionepm.org.co"

_AVISO_BORRADOR = (
    '<p style="background:#fff3cd;border:1px solid #ffe69c;padding:.75rem 1rem;'
    'border-radius:.375rem"><strong>Aviso:</strong> este texto es un borrador '
    "generado para completar el registro de la app de WhatsApp Business ante "
    "Meta. La Fundación todavía no ha designado un responsable del tratamiento "
    "de datos (ver CLAUDE.md §11); el contacto y los detalles deben ser "
    "revisados y confirmados por esa persona antes de considerarse "
    "definitivos.</p>"
)


@router.get("/privacidad", response_class=HTMLResponse, include_in_schema=False)
async def privacy_policy() -> str:
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<title>Política de privacidad — {_RAZON_SOCIAL}</title></head>
<body style="font-family:sans-serif;max-width:40rem;margin:2rem auto;line-height:1.5">
<h1>Política de privacidad</h1>
{_AVISO_BORRADOR}
<p><strong>Responsable del tratamiento:</strong> {_RAZON_SOCIAL}, NIT {_NIT},
Medellín, Colombia.</p>
<h2>¿Qué datos recogemos?</h2>
<p>Cuando escribís al bot de WhatsApp de la Fundación, guardamos tu número de
teléfono, tu nombre de perfil de WhatsApp y el contenido de los mensajes que
enviás, únicamente para poder responder tu consulta sobre la programación
cultural (Biblioteca EPM, Museo del Agua, Parque de los Deseos / Casa de la
Música y las UVA).</p>
<h2>¿Para qué los usamos?</h2>
<p>Solo para responder tus preguntas sobre horarios, actividades, tarifas y
requisitos de la programación cultural, y para mejorar ese servicio. No
vendemos ni compartimos tus datos con terceros con fines comerciales.</p>
<h2>Tus derechos (Ley 1581 de 2012, Colombia)</h2>
<p>Podés conocer, actualizar, rectificar y solicitar la eliminación de tus
datos personales en cualquier momento. Ver
<a href="/eliminar-datos">cómo solicitar la eliminación de tus datos</a>.</p>
<h2>Contacto</h2>
<p>{_CONTACTO_PROVISIONAL}</p>
</body></html>"""


@router.get("/eliminar-datos", response_class=HTMLResponse, include_in_schema=False)
async def data_deletion_instructions() -> str:
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<title>Eliminación de datos — {_RAZON_SOCIAL}</title></head>
<body style="font-family:sans-serif;max-width:40rem;margin:2rem auto;line-height:1.5">
<h1>Solicitar la eliminación de tus datos</h1>
{_AVISO_BORRADOR}
<p>Si escribiste alguna vez al bot de WhatsApp de la Fundación Grupo EPM y
querés que eliminemos tu número, tu nombre de perfil y el historial de
mensajes asociado, tenés dos formas de pedirlo:</p>
<ol>
<li>Escribí <strong>"ELIMINAR MIS DATOS"</strong> por WhatsApp al mismo
número donde escribiste.</li>
<li>Escribinos a <strong>{_CONTACTO_PROVISIONAL}</strong> indicando el
número de WhatsApp desde el que escribiste.</li>
</ol>
<p>Vamos a confirmar la eliminación por el mismo canal en un plazo
razonable.</p>
</body></html>"""
