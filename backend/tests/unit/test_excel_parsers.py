"""Tests de los parsers del Excel, uno por trampa del contrato.

Cada clase corresponde a una sección de `docs/CONTRATO_EXCEL_PROGRAMACION.md`.
Los valores usados son los **observados en el archivo real** de julio 2026, no
inventados: si el formato cambia, estos tests son los que avisan.
"""

from datetime import date, time
from uuid import uuid4

import pytest

from src.application.ingestion.schemas import IngestionWarning
from src.domain.value_objects import Audience
from src.infrastructure.ingestion.excel.audience import parse_audience
from src.infrastructure.ingestion.excel.dates import (
    DateParseError,
    parse_dates,
    parse_month_year,
    parse_weekdays,
)
from src.infrastructure.ingestion.excel.headers import (
    CANONICAL_HEADERS,
    find_header_row,
    normalize,
)
from src.infrastructure.ingestion.excel.registration import parse_registration
from src.infrastructure.ingestion.excel.rooms import RoomCatalog, resolve_room
from src.infrastructure.ingestion.excel.times import TimeParseError, parse_time_range

HEADERS = (
    "Título del curso",
    "Descripción",
    "Día(s)",
    "Fecha(s)",
    "Horario",
    "Lugar",
    "Público",
    "Inscripción",
    "Enlace de inscripción",
)


class TestNormalize:
    def test_removes_accents_and_case(self) -> None:
        assert normalize("Descripción") == "descripcion"
        assert normalize("PÚBLICO") == "publico"

    def test_collapses_whitespace(self) -> None:
        assert normalize("  Sala   de   Formación  ") == "sala de formacion"

    def test_handles_non_breaking_space(self) -> None:
        """'p.\\xa0m.' aparece al copiar desde Word y rompe los parsers si no
        se normaliza."""
        assert normalize("2:00 p.\xa0m.") == "2:00 p. m."

    def test_none_is_empty(self) -> None:
        assert normalize(None) == ""


class TestHeaderDetection:
    """Contrato §1."""

    def test_finds_headers_on_row_two(self) -> None:
        rows = [("Programación infantil – Julio 2026",), HEADERS, ("A Jugar",)]
        header = find_header_row(rows)
        assert header is not None
        assert header.row_number == 2
        assert header.is_usable

    def test_finds_headers_on_row_four(self) -> None:
        """No se asume que sea la fila 2: se escanean las 10 primeras."""
        rows = [("Título",), (), ("nota suelta",), HEADERS, ("A Jugar",)]
        header = find_header_row(rows)
        assert header is not None
        assert header.row_number == 4

    def test_ignores_sheet_without_headers(self) -> None:
        """Una hoja que no es de programación se ignora, no rompe el archivo."""
        rows = [("Notas internas",), ("cualquier cosa", "otra")]
        assert find_header_row(rows) is None

    def test_accepts_synonyms(self) -> None:
        """§2: 'Actividad' vale por 'Título del curso', 'Hora' por 'Horario'."""
        synonyms = ("Actividad", "Descripción", "Días", "Fechas", "Hora", "Sala", "Dirigido a")
        header = find_header_row([synonyms])
        assert header is not None
        assert header.columns["title"] == 0
        assert header.columns["dates_raw"] == 3
        assert header.columns["time_raw"] == 4

    def test_keeps_unknown_columns(self) -> None:
        """§2: una columna desconocida se conserva, no descarta el archivo."""
        rows = [(*HEADERS, "Cupo máximo")]
        header = find_header_row(rows)
        assert header is not None
        assert "Cupo máximo" in header.unknown

    def test_every_canonical_header_maps_to_a_field(self) -> None:
        assert all(CANONICAL_HEADERS.values())


class TestDateParsing:
    """Contrato §3."""

    def test_month_year_from_sheet_title(self) -> None:
        assert parse_month_year("Programación infantil – Julio 2026") == (2026, 7)
        assert parse_month_year("Programación jóvenes y adultos – Julio 2026") == (2026, 7)

    def test_month_year_returns_none_when_absent(self) -> None:
        """Sin año en el título hay que usar el parámetro de carga, no adivinar."""
        assert parse_month_year("Programación infantil") is None
        assert parse_month_year(None) is None

    def test_single_date(self) -> None:
        result = parse_dates("01 de julio", year=2026, month=7)
        assert result.dates == [date(2026, 7, 1)]

    def test_two_dates(self) -> None:
        result = parse_dates("07 y 14 de julio", year=2026, month=7)
        assert result.dates == [date(2026, 7, 7), date(2026, 7, 14)]

    def test_three_dates_share_a_group(self) -> None:
        """§3.1: una fila con 3 fechas produce 3 actividades."""
        result = parse_dates("14, 21 y 28 de julio", year=2026, month=7)
        assert result.dates == [date(2026, 7, 14), date(2026, 7, 21), date(2026, 7, 28)]

    def test_four_dates(self) -> None:
        result = parse_dates("02, 09, 16 y 23 de julio", year=2026, month=7)
        assert len(result.dates) == 4
        assert result.dates[0] == date(2026, 7, 2)

    def test_weekly_recurrence(self) -> None:
        """'Todos los martes de julio' → los martes reales de julio de 2026."""
        result = parse_dates("Todos los martes de julio", year=2026, month=7)
        assert result.dates == [
            date(2026, 7, 7),
            date(2026, 7, 14),
            date(2026, 7, 21),
            date(2026, 7, 28),
        ]
        assert all(d.weekday() == 1 for d in result.dates)
        assert result.recurrence == "Todos los martes de julio"

    def test_range_crossing_months_expands_by_weekday(self) -> None:
        """§3.2: el rango se acota a los días de 'Día(s)'."""
        result = parse_dates(
            "Del 23 de junio al 9 de julio",
            year=2026,
            month=7,
            weekdays_raw="Martes y jueves",
        )
        assert result.dates == [
            date(2026, 6, 23),
            date(2026, 6, 25),
            date(2026, 6, 30),
            date(2026, 7, 2),
            date(2026, 7, 7),
            date(2026, 7, 9),
        ]

    def test_out_of_month_dates_are_flagged_not_discarded(self) -> None:
        """§3.3: una fecha fuera del mes se importa, no se descarta."""
        result = parse_dates(
            "Del 23 de junio al 9 de julio",
            year=2026,
            month=7,
            weekdays_raw="Martes y jueves",
        )
        assert result.out_of_month == [date(2026, 6, 23), date(2026, 6, 25), date(2026, 6, 30)]
        assert len(result.dates) == 6  # ninguna se perdió

    def test_range_without_weekdays_expands_to_all_days(self) -> None:
        result = parse_dates("Del 1 de julio al 5 de julio", year=2026, month=7)
        assert len(result.dates) == 5

    def test_impossible_date_is_a_row_error(self) -> None:
        """§3.4: el 31 de febrero es error de fila, no del archivo."""
        with pytest.raises(DateParseError, match="imposible"):
            parse_dates("31 de febrero", year=2026, month=2)

    def test_empty_cell_is_an_error(self) -> None:
        with pytest.raises(DateParseError):
            parse_dates("", year=2026, month=7)

    def test_unrecognized_format_is_an_error(self) -> None:
        """Ante algo que no entiende, falla explícito en vez de adivinar."""
        with pytest.raises(DateParseError, match="no reconocido"):
            parse_dates("cuando se pueda", year=2026, month=7)

    def test_parse_weekdays(self) -> None:
        assert parse_weekdays("Martes y jueves") == {1, 3}
        assert parse_weekdays("Miércoles") == {2}
        assert parse_weekdays(None) == set()


class TestTimeParsing:
    """Contrato §4."""

    def test_afternoon_range(self) -> None:
        result = parse_time_range("2:00 p.m. a 4:00 p.m.")
        assert result.start == time(14, 0)
        assert result.end == time(16, 0)

    def test_noon_is_twelve_not_midnight(self) -> None:
        """LA trampa del contrato: '12:00 m.' es MEDIODÍA.

        Confundirlo con medianoche desplazaría la actividad doce horas y el
        bot daría una hora falsa.
        """
        result = parse_time_range("10:00 a.m. a 12:00 m.")
        assert result.start == time(10, 0)
        assert result.end == time(12, 0)
        assert result.end != time(0, 0)

    def test_twelve_am_is_midnight(self) -> None:
        assert parse_time_range("12:00 a.m.").start == time(0, 0)

    def test_twelve_pm_is_noon(self) -> None:
        assert parse_time_range("12:00 p.m.").start == time(12, 0)

    @pytest.mark.parametrize(
        "raw",
        ["2:00 p.m.", "2:00 pm", "2:00 P.M.", "2:00 p. m.", "2:00 p.\xa0m."],
    )
    def test_accepts_pm_variants(self, raw: str) -> None:
        """Incluida la del espacio duro, que aparece al copiar de Word."""
        assert parse_time_range(raw).start == time(14, 0)

    @pytest.mark.parametrize("separator", ["a", "-", "–", "hasta"])
    def test_accepts_separators(self, separator: str) -> None:
        result = parse_time_range(f"1:30 p.m. {separator} 3:30 p.m.")
        assert result.start == time(13, 30)
        assert result.end == time(15, 30)

    def test_half_hours(self) -> None:
        result = parse_time_range("2:30 p.m. a 4:30 p.m.")
        assert result.start == time(14, 30)
        assert result.end == time(16, 30)

    def test_missing_end_stays_none(self) -> None:
        """§4: prohibido asumir una duración de dos horas."""
        result = parse_time_range("2:00 p.m.")
        assert result.start == time(14, 0)
        assert result.end is None

    def test_end_before_start_is_an_error(self) -> None:
        with pytest.raises(TimeParseError, match="anterior"):
            parse_time_range("4:00 p.m. a 2:00 p.m.")

    def test_meridiem_marker_only_valid_with_twelve(self) -> None:
        with pytest.raises(TimeParseError, match="mediodía"):
            parse_time_range("10:00 m.")

    def test_empty_is_an_error(self) -> None:
        with pytest.raises(TimeParseError):
            parse_time_range("")


class TestRoomResolution:
    """Contrato §5."""

    @pytest.fixture
    def catalog(self) -> RoomCatalog:
        return RoomCatalog.from_pairs(
            [
                ("Taller Infantil", uuid4()),
                ("Sala de formación", uuid4()),
                ("Sala de Formación 3", uuid4()),
                ("Sala de formación 4", uuid4()),
                ("Sala de Investigadores", uuid4()),
                ("Cafetería", uuid4()),
            ]
        )

    def test_case_differences_resolve_to_same_room(self, catalog: RoomCatalog) -> None:
        """'Taller Infantil' y 'Taller infantil' son la misma sala."""
        a = resolve_room("Taller Infantil", catalog)
        b = resolve_room("Taller infantil", catalog)
        assert a.room_id == b.room_id
        assert a.room_id is not None

    def test_numbered_rooms_are_different(self, catalog: RoomCatalog) -> None:
        """El número es significativo: son sitios distintos.

        Sus nombres se parecen más del 85 %, así que sin la comprobación de
        número la coincidencia difusa las fundiría.
        """
        generic = resolve_room("Sala de Formación", catalog)
        three = resolve_room("Sala de Formación 3", catalog)
        four = resolve_room("Sala de formación 4", catalog)
        assert generic.room_id != three.room_id
        assert three.room_id != four.room_id
        assert len({generic.room_id, three.room_id, four.room_id}) == 3

    @pytest.mark.parametrize(
        "sentinel",
        [
            "No especificado en el documento",
            "No especificado",
            "N/A",
            "-",
            "Por definir",
            "Pendiente",
        ],
    )
    def test_sentinels_become_null(self, sentinel: str, catalog: RoomCatalog) -> None:
        """§5: no son nombres de sala, son la ausencia de dato."""
        result = resolve_room(sentinel, catalog)
        assert result.room_id is None
        assert result.room_raw is None
        assert result.warnings == []

    def test_unknown_room_is_not_created(self, catalog: RoomCatalog) -> None:
        """§5: una sala nueva no se crea sola; queda para el panel."""
        result = resolve_room("Auditorio Nuevo", catalog)
        assert result.room_id is None
        assert result.room_raw == "Auditorio Nuevo"
        assert IngestionWarning.ROOM_UNKNOWN in result.warnings

    def test_empty_is_null_without_warning(self, catalog: RoomCatalog) -> None:
        assert resolve_room(None, catalog).room_id is None
        assert resolve_room("", catalog).warnings == []


class TestAudienceParsing:
    """Contrato §6."""

    def test_age_range(self) -> None:
        result = parse_audience("Niñas y niños de 4 a 7 años")
        assert result.age_min == 4
        assert result.age_max == 7
        assert result.audience is Audience.INFANTIL

    def test_open_ended_range(self) -> None:
        """'de 9 años en adelante' → age_max queda en None, no se inventa."""
        result = parse_audience("Niños y niñas de 9 años en adelante")
        assert result.age_min == 9
        assert result.age_max is None

    def test_keeps_raw_text_always(self) -> None:
        """El bot muestra el texto literal, que es más útil que el enum."""
        raw = "Niñas y niños de 2 a 4 años"
        assert parse_audience(raw).audience_raw == raw

    def test_adults(self) -> None:
        result = parse_audience("Jóvenes y adultos")
        assert result.audience in (Audience.JUVENIL, Audience.ADULTO)
        assert result.age_min is None
        assert result.age_max is None

    def test_never_invents_ages(self) -> None:
        result = parse_audience("Público general")
        assert result.age_min is None
        assert result.age_max is None

    def test_empty_falls_back_to_sheet_name(self) -> None:
        """§6: el nombre de la hoja es una pista, y se marca como tal."""
        result = parse_audience(None, sheet_name="Programación infantil")
        assert result.audience is Audience.INFANTIL
        assert result.from_sheet_name is True
        assert result.audience_raw is None

    def test_empty_without_hint_is_none(self) -> None:
        result = parse_audience(None)
        assert result.audience is None
        assert result.from_sheet_name is False


class TestRegistration:
    """Contrato §7: la tabla de decisión."""

    def test_no_registration_without_link(self) -> None:
        result = parse_registration("No requiere inscripción", None)
        assert result.requires_registration is False
        assert result.registration_url is None

    def test_no_registration_with_link_is_inconsistent(self) -> None:
        result = parse_registration("No requiere inscripción", "https://forms.office.com/r/abc")
        assert result.requires_registration is False
        assert IngestionWarning.REGISTRATION_INCONSISTENT in result.warnings

    def test_empty_with_link_requires_registration(self) -> None:
        result = parse_registration(None, "https://forms.office.com/r/5dx5psEj3r")
        assert result.requires_registration is True
        assert result.registration_url == "https://forms.office.com/r/5dx5psEj3r"

    def test_empty_and_empty_is_unresolved(self) -> None:
        """§7: no se asume nada. Prometer que no hace falta inscribirse
        cuando no lo sabemos es peor que admitir que no lo sabemos."""
        result = parse_registration(None, None)
        assert result.requires_registration is None
        assert IngestionWarning.REGISTRATION_UNRESOLVED in result.warnings

    @pytest.mark.parametrize(
        "text", ["Requiere inscripción", "Con inscripción", "Cupo limitado"]
    )
    def test_explicit_requirement(self, text: str) -> None:
        assert parse_registration(text, None).requires_registration is True

    def test_non_url_text_in_link_column(self) -> None:
        """Caso real de julio 2026 que el contrato no cubría.

        'No disponible por cúpos completados' no es una URL: no puede
        guardarse en un campo de URL, pero tampoco se tira.
        """
        result = parse_registration(None, "No disponible por cúpos completados")
        assert result.registration_url is None
        assert result.requires_registration is None
        assert IngestionWarning.REGISTRATION_NOT_A_URL in result.warnings
        assert result.extra["registration_note"] == "No disponible por cúpos completados"

    def test_long_query_strings_are_preserved(self) -> None:
        """§7: la URL no se acorta ni se reescribe."""
        url = (
            "https://forms.cloud.microsoft/pages/responsepage.aspx?"
            "id=gKTnidS4j0WDAvvaARYf8t3VSwWtZFxBkqGI6cxn0TBUNFhXSlRQREhORE4yV1hNVjZHVlhNWDNQTiQlQCNjPTEkJUAjdD1n"
        )
        assert parse_registration(None, url).registration_url == url
