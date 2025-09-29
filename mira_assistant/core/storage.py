"""SQLite persistence layer built with SQLModel."""
from __future__ import annotations

import datetime as dt
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import Column, DateTime, JSON, LargeBinary
from sqlmodel import Field, Session, SQLModel, create_engine, select

from config import settings


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _ensure_utc(value: Optional[dt.datetime]) -> Optional[dt.datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(dt.timezone.utc)


class TaskStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class Task(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    status: TaskStatus = Field(default=TaskStatus.TODO)
    due_dt: Optional[dt.datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    priority: int = Field(default=0)
    tags: Optional[dict] = Field(default=None, sa_column=Column(JSON, nullable=True))
    notes: Optional[str] = Field(default=None, sa_column_kwargs={"nullable": True})
    created_at: dt.datetime = Field(default_factory=_utcnow, sa_column=Column(DateTime(timezone=True)))
    updated_at: dt.datetime = Field(default_factory=_utcnow, sa_column=Column(DateTime(timezone=True)))


class Event(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    start_dt: dt.datetime = Field(sa_column=Column(DateTime(timezone=True)))
    end_dt: Optional[dt.datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    location: Optional[str] = Field(default=None, sa_column_kwargs={"nullable": True})
    remind_policy: Optional[dict] = Field(default=None, sa_column=Column(JSON, nullable=True))
    participants: Optional[dict] = Field(default=None, sa_column=Column(JSON, nullable=True))
    link: Optional[str] = Field(default=None, sa_column_kwargs={"nullable": True})
    notes: Optional[str] = Field(default=None, sa_column_kwargs={"nullable": True})
    created_at: dt.datetime = Field(default_factory=_utcnow, sa_column=Column(DateTime(timezone=True)))


class Document(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    path: str
    title: str
    topic: Optional[str] = Field(default=None, sa_column_kwargs={"nullable": True})
    tags: Optional[dict] = Field(default=None, sa_column=Column(JSON, nullable=True))
    ingested_at: dt.datetime = Field(default_factory=_utcnow, sa_column=Column(DateTime(timezone=True)))
    checksum: str
    text_chars: Optional[int] = Field(default=None, sa_column_kwargs={"nullable": True})
    lang: Optional[str] = Field(default="tr", sa_column_kwargs={"nullable": True})


class Chunk(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    doc_id: int = Field(foreign_key="document.id")
    seq: int
    text: str
    embedding: Optional[bytes] = Field(default=None, sa_column=Column(LargeBinary, nullable=True))
    tokens: Optional[int] = Field(default=None, sa_column_kwargs={"nullable": True})


class Knowledge(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    topic: str
    fact: str
    confidence: float = Field(default=0.8)
    source: Optional[str] = Field(default=None, sa_column_kwargs={"nullable": True})
    last_revalidated: Optional[dt.datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class Meeting(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    event_id: Optional[int] = Field(default=None, foreign_key="event.id")
    audio_path: Optional[str] = Field(default=None, sa_column_kwargs={"nullable": True})
    transcript_path: Optional[str] = Field(default=None, sa_column_kwargs={"nullable": True})
    summary_md: Optional[str] = Field(default=None, sa_column_kwargs={"nullable": True})
    action_items_json: Optional[dict] = Field(default=None, sa_column=Column(JSON, nullable=True))
    decisions_json: Optional[dict] = Field(default=None, sa_column=Column(JSON, nullable=True))
    created_at: dt.datetime = Field(default_factory=_utcnow, sa_column=Column(DateTime(timezone=True)))


_engine = None


def get_engine(path: Optional[Path] = None):
    """Return a singleton SQLAlchemy engine for the configured SQLite database."""

    global _engine
    if _engine is None:
        settings.ensure_directories()
        db_path = path or settings.db_path
        _engine = create_engine(
            f"sqlite:///{db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )
    return _engine


def init_db(path: Optional[Path] = None) -> None:
    """Create the database schema and ensure directories exist."""

    settings.ensure_directories()
    engine = get_engine(path)
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    return Session(get_engine())


def add_event(session: Session, event: Event) -> Event:
    event.start_dt = _ensure_utc(event.start_dt) or _utcnow()
    event.end_dt = _ensure_utc(event.end_dt)
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def update_event(session: Session, event_id: int, updates: Dict[str, Any]) -> Optional[Event]:
    event = session.get(Event, event_id)
    if event is None:
        return None
    for key, value in updates.items():
        if key in {"start_dt", "end_dt"} and isinstance(value, dt.datetime):
            value = _ensure_utc(value)
        setattr(event, key, value)
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def delete_event(session: Session, event_id: int) -> bool:
    event = session.get(Event, event_id)
    if event is None:
        return False
    session.delete(event)
    session.commit()
    return True


def upsert_task(session: Session, task: Task) -> Task:
    task.updated_at = _utcnow()
    task.due_dt = _ensure_utc(task.due_dt)
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def complete_task(session: Session, task_id: int) -> Optional[Task]:
    task = session.get(Task, task_id)
    if task is None:
        return None
    task.status = TaskStatus.DONE
    task.updated_at = _utcnow()
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def list_events_between(session: Session, start: dt.datetime, end: dt.datetime) -> List[Event]:
    start = _ensure_utc(start) or _utcnow()
    end = _ensure_utc(end) or start
    statement = select(Event).where(Event.start_dt >= start, Event.start_dt <= end).order_by(Event.start_dt)
    return list(session.exec(statement))


def list_tasks(session: Session, *, include_completed: bool = False) -> List[Task]:
    statement = select(Task)
    if not include_completed:
        statement = statement.where(Task.status != TaskStatus.DONE)
    statement = statement.order_by(Task.due_dt.is_(None), Task.due_dt)
    return list(session.exec(statement))


def list_due_tasks(session: Session, reference: Optional[dt.datetime] = None) -> List[Task]:
    reference = _ensure_utc(reference) or _utcnow()
    statement = select(Task).where(Task.due_dt <= reference, Task.status != TaskStatus.DONE)
    statement = statement.order_by(Task.due_dt)
    return list(session.exec(statement))


def get_document_by_checksum(session: Session, checksum: str) -> Optional[Document]:
    statement = select(Document).where(Document.checksum == checksum)
    return session.exec(statement).first()


def bulk_insert_chunks(session: Session, document: Document, chunks: Sequence[Chunk]) -> None:
    for chunk in chunks:
        chunk.doc_id = document.id  # type: ignore[assignment]
        session.add(chunk)
    session.commit()


__all__ = [
    "Task",
    "TaskStatus",
    "Event",
    "Document",
    "Chunk",
    "Knowledge",
    "Meeting",
    "init_db",
    "get_session",
    "add_event",
    "update_event",
    "delete_event",
    "upsert_task",
    "complete_task",
    "list_events_between",
    "list_tasks",
    "list_due_tasks",
    "get_document_by_checksum",
    "bulk_insert_chunks",
]
