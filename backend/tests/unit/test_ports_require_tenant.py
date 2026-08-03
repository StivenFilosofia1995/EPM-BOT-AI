"""Ningún método de repositorio puede existir sin `tenant_id`.

Es una regla innegociable (CLAUDE.md §1.2) y aquí se comprueba por inspección
de firmas, no por revisión humana: quien añada mañana un método sin tenant verá
fallar el build en vez de descubrirlo cuando un tenant lea datos de otro.
"""

import inspect
from typing import Any, get_type_hints

import pytest

from src.domain.ports import ConversationRepositoryPort
from src.domain.value_objects import TenantId

#: Puertos que persisten o recuperan datos de negocio.
REPOSITORY_PORTS: tuple[type, ...] = (ConversationRepositoryPort,)


def _abstract_methods(port: Any) -> list[tuple[str, inspect.Signature]]:
    return [
        (name, inspect.signature(getattr(port, name)))
        for name in sorted(port.__abstractmethods__)
    ]


@pytest.mark.parametrize("port", REPOSITORY_PORTS, ids=lambda p: p.__name__)
def test_every_repository_method_takes_tenant_id(port: type) -> None:
    offenders = [
        name
        for name, signature in _abstract_methods(port)
        if "tenant_id" not in signature.parameters
    ]
    assert not offenders, (
        f"{port.__name__} tiene métodos sin `tenant_id`: {offenders}. "
        "Toda consulta debe filtrar por tenant (CLAUDE.md §1.2)."
    )


@pytest.mark.parametrize("port", REPOSITORY_PORTS, ids=lambda p: p.__name__)
def test_tenant_id_is_typed_as_tenant_id(port: type) -> None:
    """No basta con que se llame `tenant_id`: tiene que ser un `TenantId`.

    Aceptar un `str` o un `UUID` sueltos invitaría a pasar el identificador
    equivocado sin que el tipado lo detecte.
    """
    wrong: list[str] = []
    for name, _ in _abstract_methods(port):
        hints = get_type_hints(getattr(port, name))
        if hints.get("tenant_id") is not TenantId:
            wrong.append(f"{name}: {hints.get('tenant_id')}")
    assert not wrong, f"{port.__name__} declara tenant_id con un tipo distinto de TenantId: {wrong}"


@pytest.mark.parametrize("port", REPOSITORY_PORTS, ids=lambda p: p.__name__)
def test_tenant_id_is_the_first_parameter(port: type) -> None:
    """Por convención va primero tras `self`: hace evidente en la llamada que
    la operación está acotada a un tenant."""
    wrong = []
    for name, signature in _abstract_methods(port):
        params = [p for p in signature.parameters if p != "self"]
        if params and params[0] != "tenant_id":
            wrong.append(f"{name}({', '.join(params)})")
    assert not wrong, f"{port.__name__}: `tenant_id` no es el primer parámetro en {wrong}"


def test_the_check_would_catch_a_violation() -> None:
    """Verifica que el propio test detecta lo que dice detectar.

    Sin esto, un fallo en la inspección haría que todos los tests de arriba
    pasaran en vacío y la regla quedaría sin vigilar.
    """
    from abc import ABC, abstractmethod  # noqa: PLC0415

    class PortMalo(ABC):
        @abstractmethod
        async def find_all(self) -> list[str]: ...

    offenders = [
        name
        for name, signature in _abstract_methods(PortMalo)
        if "tenant_id" not in signature.parameters
    ]
    assert offenders == ["find_all"]
