"""Value objects del dominio: inmutables, validados y sin dependencias externas."""

from src.domain.value_objects.conversation_window import (
    WINDOW_DURATION,
    ConversationWindow,
)
from src.domain.value_objects.identifiers import TenantId, WaId, Wamid
from src.domain.value_objects.primitives import (
    Audience,
    Confidence,
    DateRange,
    Money,
)

__all__ = [
    "WINDOW_DURATION",
    "Audience",
    "Confidence",
    "ConversationWindow",
    "DateRange",
    "Money",
    "TenantId",
    "WaId",
    "Wamid",
]
