"""Publicación por lote: el informe y el parser de mes.

La consulta en sí necesita base de datos y se prueba en integración; acá se
cubre lo que decide qué ve el operador antes de confirmar, que es la garantía
que reemplaza a la pantalla de revisión (ADR 005).
"""

import pytest

from src.application.knowledge.publish_activities import PublishResult, _parse_month


def _result(**overrides: object) -> PublishResult:
    base: dict[str, object] = {
        "tenant_slug": "fundacion-epm",
        "venue_slug": "biblioteca-epm",
        "month": "2026-07",
        "candidates": 50,
        "with_warnings": 1,
        "published": 0,
        "confirmed": False,
        "warning_kinds": {"out_of_month": 3, "registro_no_es_url": 1},
    }
    base.update(overrides)
    return PublishResult(**base)  # type: ignore[arg-type]


class TestRender:
    def test_a_dry_run_says_clearly_that_nothing_was_published(self) -> None:
        text = _result().render()

        assert "SIMULACIÓN" in text
        assert "--confirm" in text
        assert "✅" not in text

    def test_a_dry_run_lists_the_warnings_so_the_operator_can_decide(self) -> None:
        """Es lo que sustituye a la revisión visual: si no se ven las
        advertencias, confirmar sería a ciegas."""
        text = _result().render()

        assert "out_of_month: 3" in text
        assert "registro_no_es_url: 1" in text

    def test_a_confirmed_run_reports_how_many_were_published(self) -> None:
        text = _result(confirmed=True, published=50).render()

        assert "50 publicadas" in text
        assert "SIMULACIÓN" not in text

    def test_nothing_to_publish_is_stated_plainly(self) -> None:
        text = _result(candidates=0, with_warnings=0, warning_kinds={}).render()

        assert "No hay actividades en borrador" in text

    def test_without_a_venue_the_scope_says_all_of_them(self) -> None:
        assert "todos los espacios" in _result(venue_slug=None).render()


class TestParseMonth:
    def test_parses_a_valid_month(self) -> None:
        assert _parse_month("2026-07") == (2026, 7)

    @pytest.mark.parametrize("raw", ["julio", "2026/07", "2026", ""])
    def test_rejects_a_malformed_month(self, raw: str) -> None:
        with pytest.raises(ValueError, match="AAAA-MM"):
            _parse_month(raw)

    @pytest.mark.parametrize("raw", ["2026-13", "2026-00"])
    def test_rejects_a_month_out_of_range(self, raw: str) -> None:
        with pytest.raises(ValueError, match="fuera de rango"):
            _parse_month(raw)
