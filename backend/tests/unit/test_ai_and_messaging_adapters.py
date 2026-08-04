"""Los adaptadores concretos de IA y de mensajería se niegan a construirse
sin las credenciales que necesitan — mejor fallar al arrancar que a mitad de
una conversación con un usuario real."""

import pytest

from src.config.settings import get_settings
from src.infrastructure.ai.anthropic_adapter import AnthropicAdapter
from src.infrastructure.meta.messaging_adapter import MetaMessagingAdapter


def test_anthropic_adapter_requires_an_api_key() -> None:
    settings = get_settings().model_copy(update={"anthropic_api_key": None})

    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        AnthropicAdapter(settings)


def test_anthropic_adapter_builds_with_an_api_key() -> None:
    settings = get_settings().model_copy(update={"anthropic_api_key": "sk-test-dummy"})

    adapter = AnthropicAdapter(settings)

    assert adapter is not None


def test_meta_messaging_adapter_requires_access_token_and_phone_number_id() -> None:
    settings = get_settings().model_copy(
        update={"meta_access_token": None, "meta_phone_number_id": "123"}
    )

    with pytest.raises(ValueError, match="META_ACCESS_TOKEN"):
        MetaMessagingAdapter(settings)


def test_meta_messaging_adapter_builds_with_credentials() -> None:
    settings = get_settings().model_copy(
        update={"meta_access_token": "token-de-prueba", "meta_phone_number_id": "123"}
    )

    adapter = MetaMessagingAdapter(settings)

    assert adapter is not None
