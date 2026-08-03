"""Repositorios. Todos parten de `BaseTenantRepository`: no hay forma de
consultar datos de negocio sin tenant."""

from src.infrastructure.repositories.base import BaseTenantRepository
from src.infrastructure.repositories.conversations import SqlAlchemyConversationRepository

__all__ = ["BaseTenantRepository", "SqlAlchemyConversationRepository"]
