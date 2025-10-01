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

_TIME_PATTERN = re.compile(r"(\d{1,2}[:. ]\d{2})|(saat\s*\d{1,2})", re.IGNORECASE)
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

    settings_dict = DEFAULT_SETTINGS.copy()
    if reference is not None:
        settings_dict["RELATIVE_BASE"] = reference
    parsed = dateparser.parse(normalised, languages=["tr"], settings=settings_dict)
    if not isinstance(parsed, dt.datetime):
        # dateparser struggles with longer natural language phrases such as
        # "yarın saat 10'da toplantı var" and returns ``None``. When this
        # happens we fallback to ``search_dates`` which scans the string for
        # fragments that look like a datetime expression. The first match is
        # used as the parsed value.
        matches = search_dates(normalised, languages=["tr"], settings=settings_dict) or []
        if matches:
            parsed = matches[0][1]
        else:
            return None
    if default_hour is not None and not _has_explicit_time(text):
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
    return bool(_TIME_PATTERN.search(text))


__all__ = ["parse_datetime", "to_utc"]
