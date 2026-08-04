"""Verificación de la firma de los webhooks de Meta.

Meta firma cada entrega con HMAC SHA-256 del **cuerpo crudo** usando el
secreto de la app, y lo manda en `X-Hub-Signature-256`. Sin esta comprobación,
cualquiera que conozca la URL podría inventarse mensajes: el bot respondería a
conversaciones que nunca existieron y guardaríamos datos falsos.
"""

import hashlib
import hmac

#: Prefijo con el que Meta anuncia el algoritmo.
PREFIX = "sha256="


def is_valid_signature(*, body: bytes, header: str | None, app_secret: str) -> bool:
    """¿La firma corresponde a este cuerpo y a este secreto?

    Se firma el cuerpo **tal cual llegó**, sin decodificar ni reserializar: un
    JSON que se parsea y se vuelve a generar cambia espacios y orden de claves,
    y la firma deja de coincidir aunque el contenido sea el mismo.

    Args:
        body: Bytes exactos del cuerpo de la petición.
        header: Valor de `X-Hub-Signature-256`, con el prefijo `sha256=`.
        app_secret: `META_APP_SECRET`.

    Returns:
        `True` solo si la firma es válida.
    """
    if not header or not header.startswith(PREFIX):
        return False

    expected = hmac.new(
        app_secret.encode("utf-8"), msg=body, digestmod=hashlib.sha256
    ).hexdigest()

    # Comparación en tiempo constante: con `==` el tiempo de respuesta filtra
    # cuántos caracteres iniciales acertó quien lo intenta, y eso permite
    # reconstruir la firma byte a byte.
    return hmac.compare_digest(header[len(PREFIX) :], expected)
