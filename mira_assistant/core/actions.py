"""Action dispatcher turning intents into database operations."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Dict, Optional

from sqlmodel import Session, select

from .advisor import collect_daily_warnings, detect_conflicts
from .intent import Action
from .scheduler import ReminderScheduler
from .storage import (
    Chunk,
    Document,
    Event,
    Note,
    Task,
    TaskStatus,
    add_event,
    add_note,
    complete_task,
    delete_event,
    get_session,
    init_db,
    list_events_between,
    list_tasks,
    upsert_task,
)
from .summarizer import generate_summary
from .vector_store import VectorStore
from ..io.ingest import DocumentIngestor


@dataclass
class ActionResult:
    intent: str
    data: Dict[str, Any]


class ActionDispatcher:
    """Coordinate storage, scheduler and ingest subsystems."""

    def __init__(self, *, scheduler: Optional[ReminderScheduler] = None, vector_store: Optional[VectorStore] = None) -> None:
        self.scheduler = scheduler or ReminderScheduler()
        self.vector_store = vector_store or VectorStore()
        self.ingestor = DocumentIngestor(vector_store=self.vector_store)
        init_db()

    def run(self, action: Action) -> ActionResult:
        handler = getattr(self, f"handle_{action.intent}", None)
        if handler is None:
            raise NotImplementedError(f"Intent {action.intent} is not supported")
        data = handler(action.payload)
        return ActionResult(intent=action.intent, data=data)

    # Event handlers
    def handle_add_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        start = _parse_iso(payload.get("start"))
        end = _parse_iso(payload.get("end"))
        event = Event(
            title=payload.get("title", "Etkinlik"),
            start_dt=start or dt.datetime.now(dt.timezone.utc),
            end_dt=end,
            location=payload.get("location"),
            remind_policy=payload.get("remind_policy"),
            participants=payload.get("participants"),
            link=payload.get("link"),
            notes=payload.get("notes"),
        )
        with get_session() as session:
            event = add_event(session, event)
            warnings = detect_conflicts(session, event)
        jobs = self.scheduler.schedule_event_reminders(event, event.remind_policy)
        return {"event_id": event.id, "warnings": warnings, "jobs": jobs}

    def handle_update_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        event_id = int(payload.get("event_id", 0))
        updates: Dict[str, Any] = {}
        if "start" in payload:
            updates["start_dt"] = _parse_iso(payload["start"])
        if "end" in payload:
            updates["end_dt"] = _parse_iso(payload["end"])
        if "title" in payload:
            updates["title"] = payload["title"]
        with get_session() as session:
            event = session.get(Event, event_id)
            if event is None:
                return {"updated": False}
            for key, value in updates.items():
                setattr(event, key, value)
            session.add(event)
            session.commit()
            session.refresh(event)
        self.scheduler.cancel_event_reminders(event_id)
        self.scheduler.schedule_event_reminders(event, event.remind_policy)
        if hasattr(event, "model_dump"):
            payload = event.model_dump()  # type: ignore[attr-defined]
        else:
            payload = event.dict()
        return {"updated": True, "event": payload}

    def handle_delete_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        event_id = int(payload.get("event_id", 0))
        with get_session() as session:
            deleted = delete_event(session, event_id)
        if deleted:
            self.scheduler.cancel_event_reminders(event_id)
        return {"deleted": deleted}

    def handle_note(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        text = str(payload.get("text") or "").strip()
        if not text:
            return {"saved": False, "note_id": None}

        title = payload.get("title")
        if not title:
            first_line = text.splitlines()[0].strip()
            title = first_line or "Not"
        title = title[:80]

        note = Note(title=title, content=text)
        with get_session() as session:
            note = add_note(session, note)
        return {"saved": True, "note_id": note.id}

    def handle_list_events(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = dt.datetime.now(dt.timezone.utc)
        range_hint = str(payload.get("range") or "week").lower()

        if isinstance(payload.get("range"), (int, float)):
            # Allow callers to provide explicit day offsets.
            end = now + dt.timedelta(days=float(payload["range"]))
        elif range_hint in {"today", "bugun", "bugün"}:
            end = now + dt.timedelta(days=1)
        elif range_hint in {"month", "upcoming", "30d"}:
            end = now + dt.timedelta(days=30)
        elif range_hint in {"all", "future"}:
            end = now + dt.timedelta(days=365)
        else:  # default to a 7 day window
            end = now + dt.timedelta(days=7)
        with get_session() as session:
            events = list_events_between(session, now, end)
        return {
            "events": [
                {
                    "id": event.id,
                    "title": event.title,
                    "start_dt": event.start_dt.isoformat(),
                    "end_dt": event.end_dt.isoformat() if event.end_dt else None,
                    "location": event.location,
                }
                for event in events
            ]
        }

    # Task handlers
    def handle_add_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        task = Task(
            title=payload.get("title", "Görev"),
            due_dt=_parse_iso(payload.get("due")),
            priority=payload.get("priority", 0),
            tags=payload.get("tags"),
            notes=payload.get("notes"),
        )
        with get_session() as session:
            task = upsert_task(session, task)
        return {"task_id": task.id}

    def handle_update_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        task_id = int(payload.get("task_id", 0))
        with get_session() as session:
            task = session.get(Task, task_id)
            if task is None:
                return {"updated": False}
            if "title" in payload:
                task.title = payload["title"]
            if "due" in payload:
                task.due_dt = _parse_iso(payload["due"])
            if "status" in payload:
                task.status = TaskStatus(payload["status"])
            session.add(task)
            session.commit()
            session.refresh(task)
        if hasattr(task, "model_dump"):
            payload = task.model_dump()  # type: ignore[attr-defined]
        else:
            payload = task.dict()
        return {"updated": True, "task": payload}

    def handle_complete_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        task_id = int(payload.get("task_id", 0))
        with get_session() as session:
            task = complete_task(session, task_id)
        return {"completed": task is not None}

    def handle_list_tasks(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        include_completed = payload.get("include_completed", False)
        with get_session() as session:
            tasks = list_tasks(session, include_completed=include_completed)
        return {
            "tasks": [
                {
                    "id": task.id,
                    "title": task.title,
                    "due_dt": task.due_dt.isoformat() if task.due_dt else None,
                    "status": task.status.value,
                }
                for task in tasks
            ]
        }

    # Reminder handler
    def handle_schedule_reminder(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        remind_at = _parse_iso(payload.get("remind_at"))
        title = payload.get("message", "Hatırlatma")
        event = Event(title=title, start_dt=remind_at or dt.datetime.now(dt.timezone.utc))
        event.id = -1
        jobs = self.scheduler.schedule_event_reminders(event, [0])
        return {"jobs": jobs}

    # Ingest & summary
    def handle_ingest_docs(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        topic = payload.get("topic") or "Genel"
        processed = self.ingestor.process_inbox(topic)
        return {"ingested": processed}

    def handle_summarize_topic(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        topic = payload["topic"]
        with get_session() as session:
            document_stmt = select(Document).where(Document.topic == topic).order_by(Document.ingested_at.desc())
            documents = list(session.exec(document_stmt))
            chunks: list[str] = []
            for document in documents:
                chunk_stmt = select(Chunk).where(Chunk.doc_id == document.id).order_by(Chunk.seq)
                chunks.extend(chunk.text for chunk in session.exec(chunk_stmt))
        summary = generate_summary(topic, chunks)
        return {"topic": topic, "summary": summary}

    def handle_advise_on_topic(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with get_session() as session:
            warnings = collect_daily_warnings(session)
        return {"warnings": warnings}


def _parse_iso(value: Any) -> Optional[dt.datetime]:
    if not value:
        return None
    if isinstance(value, dt.datetime):
        return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)
    try:
        parsed = dt.datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


__all__ = ["ActionDispatcher", "ActionResult"]
