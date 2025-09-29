"""Data access layer built on top of SQLModel."""
from __future__ import annotations

import datetime as dt
from enum import Enum
from pathlib import Path
from typing import List, Optional

from sqlmodel import Field, SQLModel, Session, create_engine, select
from sqlalchemy import Column, JSON, LargeBinary

from config import settings


class TaskStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class Task(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    status: TaskStatus = Field(default=TaskStatus.TODO)
    due_dt: Optional[dt.datetime] = Field(default=None, sa_column_kwargs={"nullable": True})
    priority: int = Field(default=0, ge=0, le=3)
    tags: Optional[str] = Field(default=None, sa_column_kwargs={"nullable": True})
    notes: Optional[str] = Field(default=None, sa_column_kwargs={"nullable": True})
    source: str = Field(default="text")
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.utcnow())
    updated_at: dt.datetime = Field(default_factory=lambda: dt.datetime.utcnow())


class Event(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    start_dt: dt.datetime
    end_dt: Optional[dt.datetime] = Field(default=None, sa_column_kwargs={"nullable": True})
    location: Optional[str] = Field(default=None, sa_column_kwargs={"nullable": True})
    remind_policy: Optional[dict] = Field(default=None, sa_column=Column(JSON, nullable=True))
    participants: Optional[dict] = Field(default=None, sa_column=Column(JSON, nullable=True))
    link: Optional[str] = Field(default=None, sa_column_kwargs={"nullable": True})
    notes: Optional[str] = Field(default=None, sa_column_kwargs={"nullable": True})
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.utcnow())


class Document(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    path: str
    title: str
    topic: Optional[str] = Field(default=None, sa_column_kwargs={"nullable": True})
    tags: Optional[dict] = Field(default=None, sa_column=Column(JSON, nullable=True))
    ingested_at: dt.datetime = Field(default_factory=lambda: dt.datetime.utcnow())
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
    last_revalidated: Optional[dt.datetime] = Field(default=None, sa_column_kwargs={"nullable": True})


class Meeting(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    event_id: Optional[int] = Field(default=None, foreign_key="event.id")
    audio_path: Optional[str] = Field(default=None, sa_column_kwargs={"nullable": True})
    transcript_path: Optional[str] = Field(default=None, sa_column_kwargs={"nullable": True})
    summary_md: Optional[str] = Field(default=None, sa_column_kwargs={"nullable": True})
    action_items_json: Optional[dict] = Field(default=None, sa_column=Column(JSON, nullable=True))
    decisions_json: Optional[dict] = Field(default=None, sa_column=Column(JSON, nullable=True))
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.utcnow())


_engine = None


def get_engine(path: Optional[Path] = None):
    """Return a singleton SQLAlchemy engine for the SQLite database."""
    global _engine
    if _engine is None:
        settings.ensure_directories()
        db_path = path or settings.db_path
        _engine = create_engine(
            f"sqlite:///{db_path}", echo=False, connect_args={"check_same_thread": False}
        )
    return _engine


def init_db(path: Optional[Path] = None) -> None:
    """Create database tables according to the SQLModel metadata."""
    engine = get_engine(path)
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    """Return a session bound to the configured engine."""
    engine = get_engine()
    return Session(engine)


def upsert_task(session: Session, task: Task) -> Task:
    """Insert or update a task and maintain the updated timestamp."""
    task.updated_at = dt.datetime.utcnow()
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def add_event(session: Session, event: Event) -> Event:
    """Persist an event to the database."""
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def list_due_tasks(session: Session, reference: Optional[dt.datetime] = None) -> List[Task]:
    """Return tasks with due dates on or before the reference datetime."""
    if reference is None:
        reference = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)
    elif reference.tzinfo is None:
        reference = reference.replace(tzinfo=dt.timezone.utc)
    tasks = list(session.exec(select(Task)))
    due_tasks: List[Task] = []
    for task in tasks:
        if task.due_dt is None:
            continue
        due_dt = task.due_dt
        if due_dt.tzinfo is None:
            due_dt = due_dt.replace(tzinfo=dt.timezone.utc)
        if due_dt <= reference and task.status != TaskStatus.DONE:
            due_tasks.append(task)
    due_tasks.sort(key=lambda task: task.due_dt or dt.datetime.max)
    return due_tasks


def fetch_events_between(
    session: Session, start: dt.datetime, end: dt.datetime
) -> List[Event]:
    statement = select(Event).where(Event.start_dt < end, (Event.end_dt.is_(None)) | (Event.end_dt > start))
    return list(session.exec(statement))


__all__ = [
    "Task",
    "Event",
    "Document",
    "Chunk",
    "Knowledge",
    "Meeting",
    "TaskStatus",
    "init_db",
    "get_session",
    "add_event",
    "upsert_task",
    "list_due_tasks",
    "fetch_events_between",
]
