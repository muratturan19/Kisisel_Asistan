"""Rule based advisor warnings for the assistant UI."""
from __future__ import annotations

import datetime as dt
from typing import List

from sqlmodel import Session, select

from .storage import Document, Event, list_due_tasks


def detect_conflicts(session: Session, candidate: Event) -> List[str]:
    """Return textual warnings for overlapping events."""

    if candidate.start_dt is None:
        return []
    start = candidate.start_dt
    end = candidate.end_dt or (candidate.start_dt + dt.timedelta(hours=1))
    if start.tzinfo is None:
        start = start.replace(tzinfo=dt.timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=dt.timezone.utc)
    statement = select(Event).where(Event.start_dt < end, Event.end_dt.is_(None) | (Event.end_dt > start))
    warnings: List[str] = []
    for event in session.exec(statement):
        if event.id == candidate.id:
            continue
        warnings.append(
            f"Çakışma: '{event.title}' etkinliği {event.start_dt.astimezone(dt.timezone.utc).isoformat()} zamanında."  # noqa: E501
        )
    return warnings


def overdue_task_warnings(session: Session, reference: dt.datetime | None = None) -> List[str]:
    reference = reference or dt.datetime.now(dt.timezone.utc)
    tasks = list_due_tasks(session, reference)
    return [f"Geciken görev: {task.title} (son tarih {task.due_dt})" for task in tasks]


def topic_update_warnings(session: Session, horizon_hours: int = 24) -> List[str]:
    now = dt.datetime.now(dt.timezone.utc)
    horizon = now + dt.timedelta(hours=horizon_hours)
    statement = select(Event).where(Event.start_dt >= now, Event.start_dt <= horizon)
    warnings: List[str] = []
    for event in session.exec(statement):
        topic = event.title.split()[0]
        doc_stmt = select(Document).where(
            Document.topic == topic,
            Document.ingested_at >= now - dt.timedelta(days=7),
        )
        if session.exec(doc_stmt).first() is None:
            warnings.append(f"'{event.title}' toplantısı öncesi ilgili belgeler 7 gündür güncellenmedi.")
    return warnings


def collect_daily_warnings(session: Session) -> List[str]:
    warnings = overdue_task_warnings(session)
    warnings.extend(topic_update_warnings(session))
    return warnings


__all__ = [
    "detect_conflicts",
    "overdue_task_warnings",
    "topic_update_warnings",
    "collect_daily_warnings",
]
