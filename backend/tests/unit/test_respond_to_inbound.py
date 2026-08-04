"""Piezas puras del orquestador de respuesta: nada de esto toca la base de
datos, así que corre siempre, sin marcar `integration`."""

from datetime import UTC, datetime
from uuid import uuid4

from src.application.messaging.respond_to_inbound import (
    _build_ai_messages,
    _extract_text,
    _format_activities_for_prompt,
    _needs_escalation,
)
from src.domain.entities import (
    Activity,
    Message,
    MessageDirection,
    MessageStatus,
    MessageType,
    PublicationStatus,
)
from src.domain.ports.ai_provider import AIRole
from src.domain.value_objects import TenantId

TENANT_ID = TenantId(uuid4())


def _message(
    *, direction: MessageDirection, payload: dict[str, object] | None
) -> Message:
    return Message(
        id=uuid4(),
        tenant_id=TENANT_ID,
        conversation_id=uuid4(),
        direction=direction,
        type=MessageType.TEXT,
        status=MessageStatus.RECEIVED,
        payload=payload,
        created_at=datetime.now(UTC),
    )


class TestNeedsEscalation:
    def test_detects_a_complaint(self) -> None:
        assert _needs_escalation("Quiero poner una QUEJA por el servicio")

    def test_detects_a_request_to_talk_to_a_human(self) -> None:
        assert _needs_escalation("necesito hablar con una persona")

    def test_a_normal_question_does_not_escalate(self) -> None:
        assert not _needs_escalation("¿Qué actividades hay este sábado en la biblioteca?")


class TestExtractText:
    def test_extracts_body_from_an_inbound_meta_envelope(self) -> None:
        message = _message(
            direction=MessageDirection.INBOUND,
            payload={"type": "text", "text": {"body": "Hola"}},
        )
        assert _extract_text(message) == "Hola"

    def test_extracts_text_from_an_outbound_message(self) -> None:
        message = _message(
            direction=MessageDirection.OUTBOUND,
            payload={"text": "Acá tenés la programación"},
        )
        assert _extract_text(message) == "Acá tenés la programación"

    def test_a_message_without_payload_yields_none(self) -> None:
        message = _message(direction=MessageDirection.INBOUND, payload=None)
        assert _extract_text(message) is None

    def test_a_non_text_inbound_message_yields_none(self) -> None:
        message = _message(
            direction=MessageDirection.INBOUND, payload={"type": "image"}
        )
        assert _extract_text(message) is None


class TestBuildAiMessages:
    def test_orders_history_before_the_new_message_with_correct_roles(self) -> None:
        history = [
            _message(
                direction=MessageDirection.INBOUND,
                payload={"type": "text", "text": {"body": "Hola"}},
            ),
            _message(
                direction=MessageDirection.OUTBOUND,
                payload={"text": "¡Hola! ¿En qué te ayudo?"},
            ),
        ]

        messages = _build_ai_messages(history, "¿Qué hay en el Museo del Agua?")

        assert [m.role for m in messages] == [AIRole.USER, AIRole.ASSISTANT, AIRole.USER]
        assert messages[-1].content == "¿Qué hay en el Museo del Agua?"

    def test_skips_history_without_extractable_text(self) -> None:
        history = [_message(direction=MessageDirection.INBOUND, payload={"type": "image"})]

        messages = _build_ai_messages(history, "Hola")

        assert len(messages) == 1


class TestFormatActivitiesForPrompt:
    def test_says_explicitly_when_there_is_nothing(self) -> None:
        assert "No hay actividades" in _format_activities_for_prompt([])

    def test_formats_a_real_activity_without_inventing_fields(self) -> None:
        activity = Activity(
            id=uuid4(),
            tenant_id=TENANT_ID,
            venue_id=uuid4(),
            title="Club de lectura infantil",
            starts_at=datetime(2026, 8, 10, 15, 0, tzinfo=UTC),
            status=PublicationStatus.PUBLISHED,
            created_at=datetime.now(UTC),
        )

        text = _format_activities_for_prompt([activity])

        assert "Club de lectura infantil" in text
        assert "sin dato de tarifa" in text
