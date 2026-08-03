"""Tests de los value objects del dominio.

Cobertura 100 % en `domain` es obligatoria (CLAUDE.md §5), y estos objetos son
donde vive la validación que impide que un dato malo entre al sistema.
"""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from src.domain.value_objects import (
    Audience,
    Confidence,
    ConversationWindow,
    DateRange,
    Money,
    TenantId,
    WaId,
    Wamid,
)


class TestTenantId:
    def test_wraps_uuid(self) -> None:
        raw = uuid4()
        assert TenantId(raw).value == raw

    def test_from_string(self) -> None:
        raw = uuid4()
        assert TenantId.from_string(str(raw)).value == raw

    def test_rejects_garbage(self) -> None:
        with pytest.raises(ValueError, match="TenantId inválido"):
            TenantId.from_string("no-es-un-uuid")

    def test_equality_is_by_value(self) -> None:
        raw = uuid4()
        assert TenantId(raw) == TenantId(raw)


class TestWaId:
    @pytest.mark.parametrize(
        "raw",
        ["+573137501142", "+14155552671", "+442071838750"],
    )
    def test_accepts_valid_e164(self, raw: str) -> None:
        assert WaId(raw).value == raw

    def test_parse_adds_missing_plus(self) -> None:
        """Meta entrega el wa_id sin '+'; hay que normalizarlo."""
        assert WaId.parse("573137501142").value == "+573137501142"

    def test_parse_is_idempotent(self) -> None:
        assert WaId.parse("+573137501142").value == "+573137501142"

    def test_parse_strips_whitespace(self) -> None:
        assert WaId.parse("  573137501142 ").value == "+573137501142"

    @pytest.mark.parametrize(
        "raw",
        [
            "573137501142",  # sin '+'
            "+0573137501142",  # no puede empezar por 0
            "+57 313 750 1142",  # espacios
            "+57-313-750",  # guiones
            "+",  # vacío
            "+1",  # demasiado corto
            "+1234567890123456",  # 16 dígitos, se pasa de E.164
            "",
        ],
    )
    def test_rejects_invalid(self, raw: str) -> None:
        with pytest.raises(ValueError, match="E.164"):
            WaId(raw)

    def test_masked_hides_the_middle(self) -> None:
        """Los logs no pueden llevar el número en claro (CLAUDE.md §8)."""
        masked = WaId("+573137501142").masked
        assert masked == "57******1142"
        assert "3137501" not in masked

    def test_masked_of_short_number_reveals_nothing(self) -> None:
        assert set(WaId("+123456").masked) == {"*"}


class TestWamid:
    def test_accepts_meta_format(self) -> None:
        raw = "wamid.HBgMNTczMTM3NTAxMTQyFQIAEhgUM0VCMDU4RkE5"
        assert Wamid(raw).value == raw

    @pytest.mark.parametrize("raw", ["", "abc123", "wamid.", "WAMID.abc", "wamid abc"])
    def test_rejects_invalid(self, raw: str) -> None:
        with pytest.raises(ValueError, match="Wamid inválido"):
            Wamid(raw)


class TestConversationWindow:
    def test_closed_when_contact_never_wrote(self) -> None:
        """Sin mensaje entrante no hay ventana: solo plantilla."""
        now = datetime.now(UTC)
        assert ConversationWindow.closed().is_open(now) is False

    def test_open_within_24h(self) -> None:
        now = datetime.now(UTC)
        window = ConversationWindow(last_inbound_at=now - timedelta(hours=23, minutes=59))
        assert window.is_open(now) is True

    def test_closed_after_24h(self) -> None:
        now = datetime.now(UTC)
        window = ConversationWindow(last_inbound_at=now - timedelta(hours=24, seconds=1))
        assert window.is_open(now) is False

    def test_boundary_is_exclusive(self) -> None:
        """Justo a las 24:00:00 la ventana ya está cerrada."""
        now = datetime.now(UTC)
        window = ConversationWindow(last_inbound_at=now - timedelta(hours=24))
        assert window.is_open(now) is False

    def test_remaining_counts_down(self) -> None:
        now = datetime.now(UTC)
        window = ConversationWindow(last_inbound_at=now - timedelta(hours=20))
        assert window.remaining(now) == timedelta(hours=4)

    def test_remaining_is_zero_when_closed(self) -> None:
        now = datetime.now(UTC)
        assert ConversationWindow.closed().remaining(now) == timedelta(0)
        expired = ConversationWindow(last_inbound_at=now - timedelta(days=3))
        assert expired.remaining(now) == timedelta(0)

    def test_requires_timezone_aware_datetimes(self) -> None:
        with pytest.raises(ValueError, match="zona horaria"):
            ConversationWindow(last_inbound_at=datetime(2026, 8, 3, 12, 0))  # noqa: DTZ001

    def test_is_open_requires_aware_now(self) -> None:
        window = ConversationWindow.opened_at(datetime.now(UTC))
        with pytest.raises(ValueError, match="zona horaria"):
            window.is_open(datetime(2026, 8, 3, 12, 0))  # noqa: DTZ001


class TestMoney:
    def test_from_cop_converts_to_cents(self) -> None:
        assert Money.from_cop(8000).amount_cents == 800_000

    def test_rejects_negative(self) -> None:
        with pytest.raises(ValueError, match="negativos"):
            Money(amount_cents=-1)

    def test_rejects_bad_currency(self) -> None:
        with pytest.raises(ValueError, match="ISO 4217"):
            Money(amount_cents=100, currency="PESOS")

    def test_normalizes_currency_case(self) -> None:
        assert Money(amount_cents=100, currency="cop").currency == "COP"

    def test_is_free(self) -> None:
        assert Money(amount_cents=0).is_free is True
        assert Money.from_cop(8000).is_free is False

    def test_format_uses_colombian_convention(self) -> None:
        """El separador de miles en Colombia es el punto."""
        assert Money.from_cop(8000).format_es_co() == "$8.000"
        assert Money.from_cop(12000).format_es_co() == "$12.000"
        assert Money.from_cop(500000).format_es_co() == "$500.000"

    def test_format_of_zero_says_gratis(self) -> None:
        assert Money(amount_cents=0).format_es_co() == "Gratis"


class TestDateRange:
    def test_contains_bounds_inclusive(self) -> None:
        rango = DateRange(date(2026, 7, 1), date(2026, 7, 31))
        assert rango.contains(date(2026, 7, 1)) is True
        assert rango.contains(date(2026, 7, 31)) is True
        assert rango.contains(date(2026, 6, 30)) is False
        assert rango.contains(date(2026, 8, 1)) is False

    def test_contains_accepts_datetime(self) -> None:
        rango = DateRange(date(2026, 7, 1), date(2026, 7, 31))
        assert rango.contains(datetime(2026, 7, 15, 14, 30, tzinfo=UTC)) is True

    def test_days_is_inclusive(self) -> None:
        assert DateRange(date(2026, 7, 1), date(2026, 7, 31)).days == 31
        assert DateRange(date(2026, 7, 1), date(2026, 7, 1)).days == 1

    def test_rejects_inverted_range(self) -> None:
        with pytest.raises(ValueError, match="invertido"):
            DateRange(date(2026, 7, 31), date(2026, 7, 1))

    def test_range_can_cross_months(self) -> None:
        """'Del 23 de junio al 9 de julio' es un caso legítimo del contrato."""
        rango = DateRange(date(2026, 6, 23), date(2026, 7, 9))
        assert rango.days == 17
        assert rango.contains(date(2026, 6, 30)) is True


class TestConfidence:
    @pytest.mark.parametrize("value", [0.0, 0.5, 1.0])
    def test_accepts_valid_range(self, value: float) -> None:
        assert Confidence(value).value == value

    @pytest.mark.parametrize("value", [-0.01, 1.01, 2.0, -1.0])
    def test_rejects_out_of_range(self, value: float) -> None:
        with pytest.raises(ValueError, match="entre 0.0 y 1.0"):
            Confidence(value)

    def test_certain_is_one(self) -> None:
        assert Confidence.certain().value == 1.0

    def test_is_below(self) -> None:
        assert Confidence(0.7).is_below(0.8) is True
        assert Confidence(0.8).is_below(0.8) is False


class TestAudience:
    def test_values_match_contract(self) -> None:
        """Los valores son los del contrato de Excel §6."""
        assert {a.value for a in Audience} == {
            "infantil",
            "juvenil",
            "adulto",
            "familiar",
            "todo_publico",
        }

    def test_is_a_string_enum(self) -> None:
        """Se comporta como `str`: se puede serializar y comparar sin `.value`."""
        assert str(Audience.INFANTIL) == "infantil"
        assert Audience("infantil") is Audience.INFANTIL


def test_value_objects_are_immutable() -> None:
    """Frozen de verdad: nadie puede mutar un value object ya construido."""
    tenant = TenantId(UUID("00000000-0000-0000-0000-000000000001"))
    with pytest.raises((AttributeError, TypeError)):
        tenant.value = uuid4()  # type: ignore[misc]
