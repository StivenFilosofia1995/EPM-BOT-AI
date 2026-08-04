"""Tests del webhook de WhatsApp.

Dos cosas se prueban con especial cuidado:

1. **La firma.** Es lo único que separa a Meta de cualquiera que descubra la
   URL. Un fallo aquí significa aceptar mensajes inventados.
2. **Que el POST siempre devuelva 200.** Meta desactiva la suscripción tras
   varios fallos; un 500 nuestro costaría el canal entero.
"""

import hashlib
import hmac
import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.application.messaging.receive_inbound import parse_webhook
from src.config.settings import Settings, get_settings
from src.presentation.main import app
from src.presentation.routers import webhooks

APP_SECRET = "secreto-de-la-app-de-prueba"
VERIFY_TOKEN = "token-de-verificacion-de-prueba"
URL = "/api/v1/webhooks/whatsapp"


def _sign(body: bytes, secret: str = APP_SECRET) -> str:
    digest = hmac.new(secret.encode(), msg=body, digestmod=hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _settings(**overrides: Any) -> Settings:
    base = get_settings()
    return base.model_copy(
        update={
            "meta_app_secret": APP_SECRET,
            "meta_verify_token": VERIFY_TOKEN,
            **overrides,
        }
    )


@pytest.fixture
def client() -> Iterator[TestClient]:
    app.dependency_overrides[get_settings] = _settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """El webhook lee la configuración directamente, no por inyección.

    Es a propósito: el POST tiene que poder rechazar por firma **antes** de
    resolver ninguna dependencia. Por eso aquí se sustituye la función.
    """
    monkeypatch.setattr(webhooks, "get_settings", _settings)


def _payload(wamid: str = "wamid.TEST123", text: str = "Hola") -> dict[str, Any]:
    """Sobre real de Meta, con la anidación de cuatro niveles."""
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "2493807737799214",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15556706632",
                                "phone_number_id": "1283647381487618",
                            },
                            "contacts": [
                                {
                                    "profile": {"name": "Stiven"},
                                    "wa_id": "573137501142",
                                }
                            ],
                            "messages": [
                                {
                                    "from": "573137501142",
                                    "id": wamid,
                                    "timestamp": "1785859200",
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


# --- Apretón de manos (GET) ---------------------------------------------------


def test_handshake_returns_the_challenge_as_plain_text(client: TestClient) -> None:
    """Meta espera el challenge crudo. Envuelto en JSON, la verificación falla."""
    response = client.get(
        URL,
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": VERIFY_TOKEN,
            "hub.challenge": "1158201444",
        },
    )

    assert response.status_code == 200
    assert response.text == "1158201444"
    assert response.headers["content-type"].startswith("text/plain")


def test_handshake_with_the_wrong_token_is_rejected(client: TestClient) -> None:
    response = client.get(
        URL,
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "token-equivocado",
            "hub.challenge": "1158201444",
        },
    )

    assert response.status_code == 403
    assert "1158201444" not in response.text


def test_handshake_requires_mode_subscribe(client: TestClient) -> None:
    response = client.get(
        URL,
        params={
            "hub.mode": "unsubscribe",
            "hub.verify_token": VERIFY_TOKEN,
            "hub.challenge": "1158201444",
        },
    )

    assert response.status_code == 403


def test_handshake_is_disabled_without_a_configured_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        webhooks, "get_settings", lambda: _settings(meta_verify_token=None)
    )

    response = client.get(
        URL, params={"hub.mode": "subscribe", "hub.verify_token": "x", "hub.challenge": "y"}
    )

    assert response.status_code == 503


# --- Firma (POST) -------------------------------------------------------------


def test_a_valid_signature_is_accepted(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    stored: list[str] = []

    async def fake_resolve(pid: str) -> tuple[Any, Any]:
        import uuid  # noqa: PLC0415

        from src.domain.value_objects import TenantId  # noqa: PLC0415

        return TenantId(uuid.uuid4()), uuid.uuid4()

    async def fake_store(*, tenant_id: Any, channel_id: Any, message: Any) -> bool:
        stored.append(message.wamid)
        return True

    monkeypatch.setattr(webhooks, "_resolve_channel", fake_resolve)
    monkeypatch.setattr(webhooks, "store_inbound_message", fake_store)

    body = json.dumps(_payload()).encode()
    response = client.post(
        URL, content=body, headers={"X-Hub-Signature-256": _sign(body)}
    )

    assert response.status_code == 200
    assert stored == ["wamid.TEST123"]


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        "sha256=0000000000000000000000000000000000000000000000000000000000000000",
        "deadbeef",  # sin el prefijo sha256=
        "sha1=abc",
    ],
)
def test_an_invalid_signature_is_rejected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, header: str | None
) -> None:
    """Sin firma válida no se procesa nada: podría venir de cualquiera."""

    async def explode(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("No debería haberse procesado")

    monkeypatch.setattr(webhooks, "_resolve_channel", explode)

    body = json.dumps(_payload()).encode()
    headers = {} if header is None else {"X-Hub-Signature-256": header}
    response = client.post(URL, content=body, headers=headers)

    assert response.status_code == 403


def test_a_signature_from_a_different_secret_is_rejected(client: TestClient) -> None:
    body = json.dumps(_payload()).encode()

    response = client.post(
        URL,
        content=body,
        headers={"X-Hub-Signature-256": _sign(body, secret="otro-secreto")},
    )

    assert response.status_code == 403


def test_a_modified_body_invalidates_the_signature(client: TestClient) -> None:
    """La firma cubre el cuerpo: cambiar un byte la rompe."""
    original = json.dumps(_payload()).encode()
    signature = _sign(original)
    tampered = json.dumps(_payload(text="Otra cosa")).encode()

    response = client.post(
        URL, content=tampered, headers={"X-Hub-Signature-256": signature}
    )

    assert response.status_code == 403


def test_the_webhook_is_disabled_without_an_app_secret(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(webhooks, "get_settings", lambda: _settings(meta_app_secret=None))

    body = json.dumps(_payload()).encode()
    response = client.post(URL, content=body, headers={"X-Hub-Signature-256": _sign(body)})

    assert response.status_code == 503


# --- Enganche con la respuesta (P4, segundo corte) ---------------------------


def test_a_new_text_message_triggers_a_response(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    responded: list[str] = []

    async def fake_resolve(pid: str) -> tuple[Any, Any]:
        import uuid  # noqa: PLC0415

        from src.domain.value_objects import TenantId  # noqa: PLC0415

        return TenantId(uuid.uuid4()), uuid.uuid4()

    async def fake_store(**_kwargs: Any) -> bool:
        return True

    async def fake_respond(*, message_text: str, **_kwargs: Any) -> None:
        responded.append(message_text)

    monkeypatch.setattr(webhooks, "_resolve_channel", fake_resolve)
    monkeypatch.setattr(webhooks, "store_inbound_message", fake_store)
    monkeypatch.setattr(webhooks, "_respond", fake_respond)

    body = json.dumps(_payload(text="¿Qué hay este sábado?")).encode()
    response = client.post(URL, content=body, headers={"X-Hub-Signature-256": _sign(body)})

    assert response.status_code == 200
    assert responded == ["¿Qué hay este sábado?"]


def test_a_duplicate_message_does_not_trigger_a_response(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un reintento de Meta de un mensaje ya guardado no debe generar una
    segunda respuesta (CLAUDE.md §3.4)."""
    responded: list[str] = []

    async def fake_resolve(pid: str) -> tuple[Any, Any]:
        import uuid  # noqa: PLC0415

        from src.domain.value_objects import TenantId  # noqa: PLC0415

        return TenantId(uuid.uuid4()), uuid.uuid4()

    async def fake_store(**_kwargs: Any) -> bool:
        return False  # ya existía

    async def fake_respond(**_kwargs: Any) -> None:
        responded.append("no debería llamarse")

    monkeypatch.setattr(webhooks, "_resolve_channel", fake_resolve)
    monkeypatch.setattr(webhooks, "store_inbound_message", fake_store)
    monkeypatch.setattr(webhooks, "_respond", fake_respond)

    body = json.dumps(_payload()).encode()
    response = client.post(URL, content=body, headers={"X-Hub-Signature-256": _sign(body)})

    assert response.status_code == 200
    assert responded == []


def test_a_failure_while_responding_still_answers_200(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sin credenciales de IA o de Meta configuradas, `_respond` no debe
    tumbar la recepción del webhook."""

    async def fake_resolve(pid: str) -> tuple[Any, Any]:
        import uuid  # noqa: PLC0415

        from src.domain.value_objects import TenantId  # noqa: PLC0415

        return TenantId(uuid.uuid4()), uuid.uuid4()

    async def fake_store(**_kwargs: Any) -> bool:
        return True

    monkeypatch.setattr(webhooks, "_resolve_channel", fake_resolve)
    monkeypatch.setattr(webhooks, "store_inbound_message", fake_store)
    # `_respond` real, sin monkeypatchear: sin ANTHROPIC_API_KEY/META_ACCESS_TOKEN
    # configurados en el entorno de test, construir los adaptadores falla.

    body = json.dumps(_payload()).encode()
    response = client.post(URL, content=body, headers={"X-Hub-Signature-256": _sign(body)})

    assert response.status_code == 200


# --- Robustez: nunca un 5xx a Meta --------------------------------------------


def test_an_error_while_storing_still_answers_200(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Si esto devolviera 500, Meta acabaría desactivando la suscripción."""

    async def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("la base de datos no responde")

    monkeypatch.setattr(webhooks, "_resolve_channel", boom)

    body = json.dumps(_payload()).encode()
    response = client.post(URL, content=body, headers={"X-Hub-Signature-256": _sign(body)})

    assert response.status_code == 200


def test_an_unknown_phone_number_id_answers_200_and_stores_nothing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sin tenant resuelto no se guarda nada (CLAUDE.md §1.6)."""
    stored: list[str] = []

    async def unknown(_pid: str) -> None:
        return None

    async def fake_store(**kwargs: Any) -> bool:
        stored.append("guardado")
        return True

    monkeypatch.setattr(webhooks, "_resolve_channel", unknown)
    monkeypatch.setattr(webhooks, "store_inbound_message", fake_store)

    body = json.dumps(_payload()).encode()
    response = client.post(URL, content=body, headers={"X-Hub-Signature-256": _sign(body)})

    assert response.status_code == 200
    assert stored == []


def test_a_status_event_without_messages_answers_200(client: TestClient) -> None:
    """Los acuses de entrega llegan por el mismo campo y no son un error."""
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "2493807737799214",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": "1283647381487618"},
                            "statuses": [
                                {"id": "wamid.X", "status": "delivered"}
                            ],
                        },
                    }
                ],
            }
        ],
    }
    body = json.dumps(payload).encode()

    response = client.post(URL, content=body, headers={"X-Hub-Signature-256": _sign(body)})

    assert response.status_code == 200


def test_an_unparseable_body_answers_200(client: TestClient) -> None:
    body = b"esto no es json"

    response = client.post(URL, content=body, headers={"X-Hub-Signature-256": _sign(body)})

    assert response.status_code == 200


# --- Lectura del sobre de Meta ------------------------------------------------


def test_parse_extracts_the_message_fields() -> None:
    [message] = parse_webhook(_payload(text="¿Qué hay el sábado?"))

    assert message.wamid == "wamid.TEST123"
    assert message.wa_id == "573137501142"
    assert message.phone_number_id == "1283647381487618"
    assert message.type == "text"
    assert message.text == "¿Qué hay el sábado?"
    assert message.profile_name == "Stiven"
    assert message.timestamp.year == 2026


def test_parse_ignores_events_that_are_not_messages() -> None:
    assert parse_webhook({"object": "whatsapp_business_account", "entry": []}) == []
    assert parse_webhook({}) == []


def test_parse_handles_several_messages_in_one_delivery() -> None:
    """Meta agrupa: una entrega puede traer varios mensajes."""
    payload = _payload()
    payload["entry"][0]["changes"][0]["value"]["messages"].append(
        {
            "from": "573137501142",
            "id": "wamid.TEST456",
            "timestamp": "1785859260",
            "type": "image",
        }
    )

    messages = parse_webhook(payload)

    assert [m.wamid for m in messages] == ["wamid.TEST123", "wamid.TEST456"]
    assert messages[1].type == "image"
    assert messages[1].text is None


def test_parse_skips_messages_without_id_or_sender() -> None:
    payload = _payload()
    payload["entry"][0]["changes"][0]["value"]["messages"] = [
        {"from": "573137501142", "type": "text"},  # sin id
        {"id": "wamid.SIN_FROM", "type": "text"},  # sin from
    ]

    assert parse_webhook(payload) == []


def test_parse_falls_back_when_the_timestamp_is_unusable() -> None:
    """Un timestamp corrupto no debe tumbar la entrega entera."""
    payload = _payload()
    payload["entry"][0]["changes"][0]["value"]["messages"][0]["timestamp"] = "ayer"

    [message] = parse_webhook(payload)

    assert message.timestamp is not None
