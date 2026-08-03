"""Puerto de mensajería. La única implementación permitida habla con la Cloud
API oficial de Meta (CLAUDE.md §1.1)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from src.domain.value_objects import TenantId, WaId, Wamid


@dataclass(frozen=True, slots=True)
class SendResult:
    """Resultado de un envío. `wamid` es nulo si el envío falló."""

    wamid: Wamid | None
    accepted: bool
    error_code: str | None = None
    error_message: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class MessagingPort(ABC):
    """Enviar mensajes y plantillas, y marcar como leído.

    Todos los métodos reciben `tenant_id`: el adaptador resuelve con él las
    credenciales del canal. Ninguna respuesta puede enviarse sin tenant
    resuelto (CLAUDE.md §1.6).
    """

    @abstractmethod
    async def send_text(
        self,
        tenant_id: TenantId,
        to: WaId,
        body: str,
        *,
        preview_url: bool = False,
    ) -> SendResult:
        """Envía texto libre. Solo válido con la ventana de 24 h abierta."""

    @abstractmethod
    async def send_template(
        self,
        tenant_id: TenantId,
        to: WaId,
        template_name: str,
        language: str,
        *,
        parameters: dict[str, Any] | None = None,
    ) -> SendResult:
        """Envía una plantilla aprobada. Es lo único permitido fuera de la
        ventana de 24 h (CLAUDE.md §3.6)."""

    @abstractmethod
    async def send_interactive(
        self,
        tenant_id: TenantId,
        to: WaId,
        body: str,
        buttons: list[str],
        *,
        header: str | None = None,
        footer: str | None = None,
    ) -> SendResult:
        """Envía un mensaje con botones de respuesta rápida."""

    @abstractmethod
    async def mark_as_read(self, tenant_id: TenantId, wamid: Wamid) -> bool:
        """Marca un mensaje entrante como leído (doble check azul)."""
