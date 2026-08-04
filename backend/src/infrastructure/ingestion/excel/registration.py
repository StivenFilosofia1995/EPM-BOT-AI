"""Tabla de decisión de inscripción (contrato §7).

| `Inscripción`                     | Enlace   | `requires_registration` |
|-----------------------------------|----------|-------------------------|
| No requiere inscripción           | vacío    | `False`                 |
| No requiere inscripción           | presente | `False` + advertencia   |
| vacío                             | presente | `True`                  |
| vacío                             | vacío    | `None` -> revisión      |
| Requiere / Con inscripción / Cupo | lo que sea | `True`                |

El caso `None` es deliberado: **no se asume nada**. Que una fila no diga nada
sobre inscripción no significa que no la requiera, y prometerle al usuario que
puede llegar sin inscribirse es peor que decirle que no lo sabemos.
"""

from dataclasses import dataclass
from urllib.parse import urlparse

from src.application.ingestion.schemas import IngestionWarning
from src.infrastructure.ingestion.excel.headers import normalize

#: Textos que significan «no hace falta inscribirse».
_NO_REGISTRATION = ("no requiere inscripcion", "sin inscripcion", "no requiere")

#: Textos que significan «sí hace falta».
_REQUIRES = (
    "requiere inscripcion",
    "con inscripcion",
    "cupo limitado",
    "cupos limitados",
    "previa inscripcion",
    "inscripcion previa",
)


@dataclass(frozen=True, slots=True)
class ParsedRegistration:
    requires_registration: bool | None
    registration_url: str | None
    warnings: list[IngestionWarning]
    extra: dict[str, str]
    """Contenido que no cabía en los campos canónicos y no se quiere perder."""


def is_valid_url(value: str) -> bool:
    """¿Es una URL utilizable?

    Se comprueba el esquema y que haya host. La URL **no se acorta ni se
    reescribe** (§7): los enlaces de Microsoft Forms traen cadenas de consulta
    larguísimas que son significativas.
    """
    try:
        parsed = urlparse(value.strip())
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def parse_registration(
    registration_raw: str | None, url_raw: str | None
) -> ParsedRegistration:
    warnings: list[IngestionWarning] = []
    extra: dict[str, str] = {}

    text = str(registration_raw).strip() if registration_raw is not None else ""
    link = str(url_raw).strip() if url_raw is not None else ""
    normalized_text = normalize(text)

    url: str | None = None
    if link:
        if is_valid_url(link):
            url = link
        else:
            # Caso real de julio 2026: la columna de enlace traía
            # «No disponible por cúpos completados». No es una URL y no puede
            # guardarse como tal, pero tampoco se tira: se conserva en `extra`
            # y la inscripción queda sin resolver para que decida una persona.
            warnings.append(IngestionWarning.REGISTRATION_NOT_A_URL)
            extra["registration_note"] = link

    has_usable_url = url is not None

    if any(phrase in normalized_text for phrase in _NO_REGISTRATION):
        if has_usable_url:
            # Dice que no requiere inscripción pero trae enlace: se respeta lo
            # que dice el texto y se avisa de la incoherencia (§7).
            warnings.append(IngestionWarning.REGISTRATION_INCONSISTENT)
        return ParsedRegistration(False, url, warnings, extra)

    if any(phrase in normalized_text for phrase in _REQUIRES):
        return ParsedRegistration(True, url, warnings, extra)

    if has_usable_url:
        # Sin texto pero con enlace: si hay dónde inscribirse, se requiere.
        return ParsedRegistration(True, url, warnings, extra)

    if text and not normalized_text.startswith("no"):
        # Texto que no encaja en ninguna categoría conocida: no se interpreta,
        # se conserva y se marca para revisión.
        extra["registration_raw"] = text
        warnings.append(IngestionWarning.REGISTRATION_UNRESOLVED)
        return ParsedRegistration(None, url, warnings, extra)

    # Vacío y vacío, o enlace inválido sin texto: sin resolver (§7).
    warnings.append(IngestionWarning.REGISTRATION_UNRESOLVED)
    return ParsedRegistration(None, url, warnings, extra)
