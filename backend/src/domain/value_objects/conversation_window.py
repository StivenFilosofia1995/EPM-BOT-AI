"""Ventana de servicio de 24 horas de WhatsApp (CLAUDE.md §3.6)."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

WINDOW_DURATION = timedelta(hours=24)


@dataclass(frozen=True, slots=True)
class ConversationWindow:
    """Ventana abierta por el último mensaje entrante del contacto.

    Fuera de la ventana solo se pueden enviar plantillas aprobadas: el dominio
    expone el estado y es el caso de uso quien decide entre mensaje libre y
    plantilla. Nunca se intenta enviar texto libre con la ventana cerrada.
    """

    last_inbound_at: datetime | None

    def __post_init__(self) -> None:
        if self.last_inbound_at is not None and self.last_inbound_at.tzinfo is None:
            raise ValueError(
                "last_inbound_at debe llevar zona horaria; en la base todo se guarda en UTC"
            )

    @property
    def expires_at(self) -> datetime | None:
        if self.last_inbound_at is None:
            return None
        return self.last_inbound_at + WINDOW_DURATION

    def is_open(self, now: datetime) -> bool:
        """¿Se puede enviar texto libre en este instante?

        Un contacto que nunca ha escrito no tiene ventana abierta: solo
        plantilla.
        """
        if now.tzinfo is None:
            raise ValueError("`now` debe llevar zona horaria")
        expires = self.expires_at
        return expires is not None and now < expires

    def remaining(self, now: datetime) -> timedelta:
        """Tiempo restante de ventana; cero si está cerrada.

        El panel lo usa para la cuenta regresiva del inbox.
        """
        expires = self.expires_at
        if expires is None or now >= expires:
            return timedelta(0)
        return expires - now

    @classmethod
    def closed(cls) -> "ConversationWindow":
        return cls(last_inbound_at=None)

    @classmethod
    def opened_at(cls, moment: datetime) -> "ConversationWindow":
        return cls(last_inbound_at=moment.astimezone(UTC))
