import datetime as dt
from zoneinfo import ZoneInfo

import pytest


IST = ZoneInfo("Europe/Istanbul")


@pytest.mark.parametrize(
    "phrase, expected",
    [
        ("Yarın saat 14 te tedarikçi toplantısı", dt.datetime(2025, 10, 3, 14, 0, tzinfo=IST)),
        ("Bugün 16 da rapor teslimi", dt.datetime(2025, 10, 2, 16, 0, tzinfo=IST)),
        ("Pazartesi 9 da kahvaltı", dt.datetime(2025, 10, 6, 9, 0, tzinfo=IST)),
    ],
)
def test_turkish_hour_suffixes_are_parsed(phrase: str, expected: dt.datetime) -> None:
    reference = dt.datetime(2025, 10, 2, 9, 0, tzinfo=IST)
    parser_tr = __import__("mira_assistant.core.parser_tr", fromlist=["parse_datetime"])

    parsed = parser_tr.parse_datetime(phrase, reference=reference)

    assert parsed == expected


def test_time_detection_handles_apostrophes() -> None:
    reference = dt.datetime(2025, 10, 2, 9, 0, tzinfo=IST)
    parser_tr = __import__("mira_assistant.core.parser_tr", fromlist=["parse_datetime"])

    parsed = parser_tr.parse_datetime("22'si saat 10:00'da tedarikçi", reference=reference)

    assert parsed.hour == 10
    assert parsed.minute == 0
    assert parsed.day == 22


def test_evening_hours_are_interpreted_as_pm() -> None:
    reference = dt.datetime(2025, 10, 2, 12, 0, tzinfo=IST)
    parser_tr = __import__("mira_assistant.core.parser_tr", fromlist=["parse_datetime"])

    parsed = parser_tr.parse_datetime("Akşam saat 9 da poyrazı terminalden al", reference=reference)

    assert parsed.hour == 21
    assert parsed.minute == 0
    assert parsed.date() == reference.date()
