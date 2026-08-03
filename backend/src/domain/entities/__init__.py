"""Entidades del dominio: dataclasses frozen, sin ORM ni dependencias externas."""

from src.domain.entities.channels import Template, WhatsAppAccount
from src.domain.entities.conversations import Contact, Conversation, Message
from src.domain.entities.enums import (
    SOURCE_PRECEDENCE,
    ChannelStatus,
    ConversationStatus,
    IngestionRunStatus,
    MessageDirection,
    MessageStatus,
    MessageType,
    PublicationStatus,
    SourceKind,
    TenantStatus,
    UserRole,
    VenueKind,
    source_rank,
)
from src.domain.entities.identity import Tenant, User
from src.domain.entities.ingestion import IngestionRun, Source
from src.domain.entities.knowledge import Activity, Room, Venue, VenueFact

__all__ = [
    "SOURCE_PRECEDENCE",
    "Activity",
    "ChannelStatus",
    "Contact",
    "Conversation",
    "ConversationStatus",
    "IngestionRun",
    "IngestionRunStatus",
    "Message",
    "MessageDirection",
    "MessageStatus",
    "MessageType",
    "PublicationStatus",
    "Room",
    "Source",
    "SourceKind",
    "Template",
    "Tenant",
    "TenantStatus",
    "User",
    "UserRole",
    "Venue",
    "VenueFact",
    "VenueKind",
    "WhatsAppAccount",
    "source_rank",
]
