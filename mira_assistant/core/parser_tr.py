"""Turkish natural language datetime parsing helpers."""
from __future__ import annotations

import datetime as dt
import re
from typing import Optional

import dateparser

from config import settings


DEFAULT_SETTINGS = {
    "DATE_ORDER": "DMY",
    "PREFER_DATES_FROM": "future",
    "TIMEZONE": settings.timezone_name,
    "RETURN_AS_TIMEZONE_AWARE": True,
    "PARSERS": ["relative-time", "custom-formats", "absolute-time"],
}

_TIME_PATTERN = re.compile(r"(\d{1,2}[:. ]\d{2})|(saat\s*\d{1,2})", re.IGNORECASE)


def parse_datetime(
    text: str,
    *,
    reference: Optional[dt.datetime] = None,
    default_hour: Optional[int] = None,
    default_minute: int = 0,
) -> Optional[dt.datetime]:
    """Parse a Turkish datetime expression and return a timezone aware value."""

    settings_dict = DEFAULT_SETTINGS.copy()
    if reference is not None:
        settings_dict["RELATIVE_BASE"] = reference
    parsed = dateparser.parse(text, languages=["tr"], settings=settings_dict)
    if not isinstance(parsed, dt.datetime):
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
