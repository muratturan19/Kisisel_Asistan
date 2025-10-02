"""Compatibility wrapper around the core storage module.

The original project structure exposed a top-level ``storage`` module.  This
file keeps that import path available while delegating all functionality to
``mira_assistant.core.storage``.  Keeping the thin wrapper avoids breaking
downstream tooling while ensuring the shared configuration is still honoured.
"""
from mira_assistant.core.storage import (  # noqa: F401
    Chunk,
    Document,
    Event,
    Knowledge,
    Meeting,
    Note,
    Task,
    TaskStatus,
    add_event,
    add_note,
    complete_task,
    delete_event,
    get_engine,
    get_session,
    init_db,
    list_events_between,
    upsert_task,
)

__all__ = [
    "Chunk",
    "Document",
    "Event",
    "Knowledge",
    "Meeting",
    "Note",
    "Task",
    "TaskStatus",
    "add_event",
    "add_note",
    "complete_task",
    "delete_event",
    "get_engine",
    "get_session",
    "init_db",
    "list_events_between",
    "upsert_task",
]
