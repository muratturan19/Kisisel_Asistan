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
    if reference is not None:
        settings_dict["RELATIVE_BASE"] = reference
    parsed: Optional[dt.datetime] = None
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
                parsed = matches[0][1]
                break
        if not isinstance(parsed, dt.datetime):
            return None
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


__all__ = ["parse_datetime", "to_utc"]
