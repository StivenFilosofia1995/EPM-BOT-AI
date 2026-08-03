"""Modelos SQLAlchemy. Se importan todos aquí para que `Base.metadata` esté
completo cuando Alembic lo lea (autogenerate y comprobaciones)."""

from src.infrastructure.database.models.base import (
    EMBEDDING_DIM,
    TENANT_SCOPED_TABLES,
    Base,
    TimestampMixin,
)
from src.infrastructure.database.models.channels import TemplateModel, WhatsAppAccountModel
from src.infrastructure.database.models.conversations import (
    ContactModel,
    ConversationModel,
    MessageModel,
)
from src.infrastructure.database.models.identity import TenantModel, UserModel
from src.infrastructure.database.models.ingestion import (
    AITraceModel,
    AuditLogModel,
    IngestionRunModel,
    SourceModel,
)
from src.infrastructure.database.models.knowledge import (
    ActivityEmbeddingModel,
    ActivityModel,
    RoomModel,
    VenueFactModel,
    VenueModel,
)

__all__ = [
    "EMBEDDING_DIM",
    "TENANT_SCOPED_TABLES",
    "AITraceModel",
    "ActivityEmbeddingModel",
    "ActivityModel",
    "AuditLogModel",
    "Base",
    "ContactModel",
    "ConversationModel",
    "IngestionRunModel",
    "MessageModel",
    "RoomModel",
    "SourceModel",
    "TemplateModel",
    "TenantModel",
    "TimestampMixin",
    "UserModel",
    "VenueFactModel",
    "VenueModel",
    "WhatsAppAccountModel",
]
