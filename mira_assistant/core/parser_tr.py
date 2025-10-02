"""Turkish natural language datetime parsing helpers."""
from __future__ import annotations

import datetime as dt
import re
from typing import Optional

import dateparser
from dateparser.search import search_dates

from config import settings


DEFAULT_SETTINGS = {
    "DATE_ORDER": "DMY",
    "PREFER_DATES_FROM": "future",
    "TIMEZONE": settings.timezone_name,
    "RETURN_AS_TIMEZONE_AWARE": True,
    "PARSERS": ["relative-time", "custom-formats", "absolute-time"],
}

_TIME_PATTERN = re.compile(
    r"(?:\d{1,2}[:. ]\d{2})|"  # 14:00, 14.00, 14 00
    r"(?:saat\s+\d{1,2}(?:\s*(?:da|de|te)\b)?)|"  # saat 14, saat 14 te
    r"(?:\d{1,2}\s+(?:da|de|te)\b)",  # 14 da, 14 de, 14 te
    re.IGNORECASE,
)
_DAY_SUFFIX_PATTERN = re.compile(r"\b(\d{1,2})\s*(?:si|sı|inci|ıncı|uncu|üncü|ncı|nci)\b", re.IGNORECASE)
_APOSTROPHE_PATTERN = re.compile(r"(\d+)'([a-zçğıöşü]+)", re.IGNORECASE)
_DATE_KEYWORDS = {
    "yarın",
    "yarinki",
    "bugün",
    "bugun",
    "dün",
    "haftaya",
    "sonraki",
    "gelecek",
    "önümüzdeki",
    "önümüzde",
    "ertesi",
}
_DAY_NAMES = {
    "pazartesi",
    "salı",
    "sali",
    "çarşamba",
    "carsamba",
    "perşembe",
    "persembe",
    "cuma",
    "cumartesi",
    "pazar",
}
_MONTH_NAMES = {
    "ocak",
    "şubat",
    "subat",
    "mart",
    "nisan",
    "mayıs",
    "mayis",
    "haziran",
    "temmuz",
    "ağustos",
    "agustos",
    "eylül",
    "eylul",
    "ekim",
    "kasım",
    "kasim",
    "aralık",
    "aralik",
}
_DATE_NUMERIC_PATTERN = re.compile(r"\b\d{1,2}\s*[/.-]\s*\d{1,2}\b")
_PERIOD_HINTS = {
    "akşam": "evening",
    "aksam": "evening",
    "akşamüstü": "evening",
    "aksamustu": "evening",
}


def _normalise_text(text: str) -> str:
    """Normalise common Turkish apostrophe usage for time phrases."""

    # Convert "10'da" -> "10 da" and ensure remaining apostrophes become spaces
    text = _APOSTROPHE_PATTERN.sub(r"\1 \2", text)
    text = text.replace("'", " ")
    return re.sub(r"\s+", " ", text).strip()


def parse_datetime(
    text: str,
    *,
    reference: Optional[dt.datetime] = None,
    default_hour: Optional[int] = None,
    default_minute: int = 0,
) -> Optional[dt.datetime]:
    """Parse a Turkish datetime expression and return a timezone aware value."""

    normalised = _normalise_text(text)

    time_match = _TIME_PATTERN.search(normalised)
    extracted_hour = None
    if time_match:
        match_text = time_match.group(0)
        hour_match = re.fullmatch(r"saat\s+(\d{1,2})(?:\s*(?:da|de|te)\b)?", match_text, re.IGNORECASE)
        if not hour_match:
            hour_match = re.fullmatch(r"(\d{1,2})\s+(?:da|de|te)\b", match_text, re.IGNORECASE)
        if hour_match:
            try:
                extracted_hour = int(hour_match.group(1))
                if not 0 <= extracted_hour <= 23:
                    extracted_hour = None
            except (TypeError, ValueError):
                extracted_hour = None
        period_hint = _detect_period_hint(normalised[: time_match.start()].lower())
        if period_hint == "evening" and extracted_hour is not None and extracted_hour < 12:
            extracted_hour += 12

    date_candidates = []
    if normalised:
        date_candidates.append(normalised)
    if time_match:
        pre_text = normalised[: time_match.start()].strip()
        post_text = normalised[time_match.end() :].strip()
        stripped = (pre_text + " " + post_text).strip()
        for candidate in (pre_text, stripped, post_text):
            if candidate and candidate not in date_candidates:
                date_candidates.append(candidate)
    day_suffix_match = _DAY_SUFFIX_PATTERN.search(normalised)

    settings_dict = DEFAULT_SETTINGS.copy()
    effective_reference = reference or dt.datetime.now(settings.timezone)
    settings_dict["RELATIVE_BASE"] = effective_reference
    parsed: Optional[dt.datetime] = None
    parsed_from_search = False
    search_match_text = ""
    for candidate in date_candidates:
        parsed = dateparser.parse(candidate, languages=["tr"], settings=settings_dict)
        if isinstance(parsed, dt.datetime):
            break
    if not isinstance(parsed, dt.datetime):
        # dateparser struggles with longer natural language phrases such as
        # "yarın saat 10'da toplantı var" and returns ``None``. When this
        # happens we fallback to ``search_dates`` which scans the string for
        # fragments that look like a datetime expression. The first match is
        # used as the parsed value.
        for candidate in date_candidates:
            matches = search_dates(candidate, languages=["tr"], settings=settings_dict) or []
            if matches:
                search_match_text, parsed = matches[0]
                parsed_from_search = True
                break
        if not isinstance(parsed, dt.datetime):
            return None
    if parsed_from_search and not _match_contains_explicit_date(search_match_text):
        parsed = parsed.replace(
            year=effective_reference.year,
            month=effective_reference.month,
            day=effective_reference.day,
        )

    if day_suffix_match:
        try:
            parsed = parsed.replace(day=int(day_suffix_match.group(1)))
        except ValueError:
            pass

    if extracted_hour is not None:
        parsed = parsed.replace(hour=extracted_hour, minute=default_minute, second=0, microsecond=0)
    elif default_hour is not None and not _has_explicit_time(text):
        parsed = parsed.replace(hour=default_hour, minute=default_minute, second=0, microsecond=0)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=settings.timezone)
    return parsed


def to_utc(value: dt.datetime) -> dt.datetime:
    """Convert a datetime to UTC ensuring timezone awareness."""

    if value.tzinfo is None:
        value = value.replace(tzinfo=settings.timezone)
    return value.astimezone(dt.timezone.utc)


def _has_explicit_time(text: str) -> bool:
    return bool(_TIME_PATTERN.search(_normalise_text(text)))


def _match_contains_explicit_date(fragment: str) -> bool:
    lowered = fragment.lower()
    if _DATE_NUMERIC_PATTERN.search(lowered):
        return True
    if any(keyword in lowered for keyword in _DATE_KEYWORDS):
        return True
    if any(day in lowered for day in _DAY_NAMES):
        return True
    if any(month in lowered for month in _MONTH_NAMES):
        return True
    return False


def _detect_period_hint(prefix: str) -> Optional[str]:
    words = prefix.split()
    if not words:
        return None
    for word in reversed(words[-3:]):
        if word in _PERIOD_HINTS:
            return _PERIOD_HINTS[word]
    return None


__all__ = ["parse_datetime", "to_utc"]
