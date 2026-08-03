"""Enumeraciones compartidas por las entidades del dominio."""

from enum import StrEnum


class TenantStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"


class UserRole(StrEnum):
    """Roles del panel (P5). `OWNER` es el único que puede facturar y borrar el tenant."""

    OWNER = "owner"
    ADMIN = "admin"
    AGENT = "agent"
    VIEWER = "viewer"


class ChannelStatus(StrEnum):
    PENDING = "pending"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    FLAGGED = "flagged"


class ConversationStatus(StrEnum):
    OPEN = "open"
    ESCALATED = "escalated"
    CLOSED = "closed"


class MessageDirection(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageType(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"
    LOCATION = "location"
    STICKER = "sticker"
    CONTACTS = "contacts"
    INTERACTIVE = "interactive"
    BUTTON = "button"
    TEMPLATE = "template"
    SYSTEM = "system"
    UNKNOWN = "unknown"


class MessageStatus(StrEnum):
    """Estados de entrega que reporta Meta, más los internos de la cola."""

    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"
    RECEIVED = "received"


class VenueKind(StrEnum):
    """Tipos de espacio de la Fundación (KB §3)."""

    MUSEO = "museo"
    BIBLIOTECA = "biblioteca"
    PARQUE = "parque"
    UVA = "uva"
    OTRO = "otro"


class PublicationStatus(StrEnum):
    """Ciclo de vida de un dato extraído: nada llega a `PUBLISHED` sin
    aprobación humana (ADR 005)."""

    DRAFT = "draft"
    IN_REVIEW = "in_review"
    PUBLISHED = "published"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class SourceKind(StrEnum):
    """Tipos de fuente de ingesta. El orden de precedencia en conflicto está
    en `SOURCE_PRECEDENCE` (ADR 009)."""

    EXCEL_ADMIN = "excel_admin"
    MANUAL = "manual"
    PDF_ISSUU = "pdf_issuu"
    VENUE_PAGE = "venue_page"
    WEB_PROGRAMACION = "web_programacion"
    NEWS = "news"


#: Precedencia en conflicto, de mayor a menor autoridad (ADR 009).
#: Cuando dos fuentes discrepan se conservan ambas versiones y decide un
#: humano en el panel; esta lista solo indica cuál se propone por defecto.
SOURCE_PRECEDENCE: tuple[SourceKind, ...] = (
    SourceKind.EXCEL_ADMIN,
    SourceKind.MANUAL,
    SourceKind.PDF_ISSUU,
    SourceKind.VENUE_PAGE,
    SourceKind.WEB_PROGRAMACION,
    SourceKind.NEWS,
)


def source_rank(kind: SourceKind) -> int:
    """Posición en la precedencia: menor número gana."""
    return SOURCE_PRECEDENCE.index(kind)


class IngestionRunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"
