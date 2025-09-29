"""Advisor utilities for conflict detection and suggestions."""
from __future__ import annotations

import datetime as dt
from typing import List

from sqlmodel import Session

from .storage import Event, fetch_events_between


def detect_conflicts(session: Session, candidate: Event) -> List[str]:
    """Return textual warnings for overlapping events."""
    if candidate.start_dt is None:
        return []
    end = candidate.end_dt or (candidate.start_dt + dt.timedelta(hours=1))
    overlapping = fetch_events_between(session, candidate.start_dt, end)
    conflicts = []
    for event in overlapping:
        if event.id == candidate.id:
            continue
        conflicts.append(
            f"Çakışma: '{event.title}' etkinliği {event.start_dt.isoformat()} zamanında zaten planlı."
        )
    return conflicts


__all__ = ["detect_conflicts"]
