"""Turkish language parsing helpers."""
from __future__ import annotations

import datetime as dt
from typing import Optional

import dateparser


DEFAULT_SETTINGS = {
    "DATE_ORDER": "DMY",
    "PREFER_DATES_FROM": "future",
    "TIMEZONE": "Europe/Istanbul",
    "RETURN_AS_TIMEZONE_AWARE": True,
    "PARSERS": ["relative-time", "custom-formats", "absolute-time"],
}


def parse_datetime(text: str, reference: Optional[dt.datetime] = None) -> Optional[dt.datetime]:
    """Parse Turkish natural language datetime expressions."""
    settings = DEFAULT_SETTINGS.copy()
    if reference is not None:
        settings["RELATIVE_BASE"] = reference
    result = dateparser.parse(text, languages=["tr"], settings=settings)
    if isinstance(result, dt.datetime):
        return result
    return None


__all__ = ["parse_datetime"]
