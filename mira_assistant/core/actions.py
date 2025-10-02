"""Action dispatcher turning intents into database operations."""
from __future__ import annotations

import datetime as dt
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

from sqlmodel import Session, select

from config import settings
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


LOGGER = logging.getLogger(__name__)


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
        LOGGER.info(
            "ActionDispatcher initialised with scheduler=%s vector_store=%s",
            type(self.scheduler).__name__,
            type(self.vector_store).__name__,
        )

    def run(self, action: Action) -> ActionResult:
        LOGGER.info("Dispatching action %s with payload %s", action.intent, action.payload)
        handler = getattr(self, f"handle_{action.intent}", None)
        if handler is None:
            raise NotImplementedError(f"Intent {action.intent} is not supported")
        data = handler(action.payload)
        LOGGER.info("Action %s finished with response %s", action.intent, data)
        return ActionResult(intent=action.intent, data=data)

    # Event handlers
    def handle_add_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Persist a new calendar event.

        Recent LLM responses occasionally return non-standard field names such as
        ``date_time`` for the start timestamp or ``event`` for the title.  Accept
        these aliases so that the command still succeeds instead of silently
        falling back to placeholders or the current time.
        """

        start_value = (
            payload.get("start")
            or payload.get("date_time")
            or payload.get("start_dt")
            or payload.get("datetime")
        )
        end_value = payload.get("end") or payload.get("end_dt") or payload.get("end_time")
        title = payload.get("title") or payload.get("event") or payload.get("name")

        start = _parse_iso(start_value)
        end = _parse_iso(end_value)
        normalized_title = (title or "Etkinlik").strip() or "Etkinlik"
        normalized_key = normalized_title.casefold()
        start_dt = start or dt.datetime.now(dt.timezone.utc)

        with get_session() as session:
            if start is not None:
                window_start = start - dt.timedelta(hours=1)
                window_end = start + dt.timedelta(hours=1)
                existing_events = session.exec(
                    select(Event).where(Event.start_dt >= window_start, Event.start_dt <= window_end)
                ).all()
            else:
                existing_events = session.exec(select(Event)).all()
            for existing in existing_events:
                existing_title = (existing.title or "").strip().casefold()
                if existing_title != normalized_key:
                    continue
                if start is None and existing.start_dt is None:
                    LOGGER.warning("Duplicate event detected without start: %s", normalized_title)
                    return {
                        "event_id": existing.id,
                        "duplicate": True,
                        "warnings": [],
                        "jobs": [],
                        "message": "Bu etkinlik zaten mevcut",
                    }
                if start is not None and existing.start_dt is not None:
                    time_diff = abs((existing.start_dt - start).total_seconds())
                    if time_diff < 3600:
                        LOGGER.warning("Duplicate event detected: %s", normalized_title)
                        return {
                            "event_id": existing.id,
                            "duplicate": True,
                            "warnings": [],
                            "jobs": [],
                            "message": "Bu etkinlik zaten mevcut",
                        }

        event = Event(
            title=normalized_title,
            start_dt=start_dt,
            end_dt=end,
            location=payload.get("location") or payload.get("place"),
            remind_policy=payload.get("remind_policy"),
            participants=payload.get("participants"),
            link=payload.get("link"),
            notes=payload.get("notes"),
        )
        LOGGER.info(
            "Creating event title=%s start=%s end=%s location=%s",
            event.title,
            event.start_dt,
            event.end_dt,
            event.location,
        )
        with get_session() as session:
            event = add_event(session, event)
            warnings = detect_conflicts(session, event)
        jobs = self.scheduler.schedule_event_reminders(event, event.remind_policy)
        LOGGER.info("Event saved with id=%s, scheduled jobs=%s", event.id, jobs)
        return {"event_id": event.id, "warnings": warnings, "jobs": jobs, "duplicate": False}

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
                LOGGER.warning("Event %s not found for update", event_id)
                return {"updated": False}
            for key, value in updates.items():
                setattr(event, key, value)
            session.add(event)
            session.commit()
            session.refresh(event)
        LOGGER.info("Event %s updated with %s", event_id, updates)
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
            LOGGER.info("Event %s deleted and reminders cancelled", event_id)
        else:
            LOGGER.warning("Delete event requested but id=%s not found", event_id)
        return {"deleted": deleted}

    def handle_note(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        text = str(
            payload.get("text")
            or payload.get("message")
            or payload.get("content")
            or payload.get("note")
            or ""
        ).strip()
        if not text:
            return {"saved": False, "note_id": None}

        title = payload.get("title") or payload.get("subject")
        if not title:
            first_line = text.splitlines()[0].strip()
            title = first_line or "Not"
        title = title[:80]

        note = Note(title=title, content=text)
        with get_session() as session:
            note = add_note(session, note)
        LOGGER.info("Note saved with id=%s", note.id)
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
        LOGGER.info("Listing events between %s and %s -> %d records", now, end, len(events))
        return {
            "events": [
                {
                    "id": event.id,
                    "title": event.title,
                    "start_dt": event.start_dt.isoformat(),
                    "end_dt": event.end_dt.isoformat() if event.end_dt else None,
                    "location": event.location,
                    "notes": event.notes,
                    "participants": event.participants,
                    "link": event.link,
                    "remind_policy": event.remind_policy,
                }
                for event in events
            ]
        }

    # Task handlers
    def handle_add_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        raw_title = str(payload.get("title", "Görev") or "")
        title = raw_title.strip() or "Görev"
        normalized_title = title.casefold()
        due_dt = _parse_iso(payload.get("due"))

        with get_session() as session:
            existing_tasks = list_tasks(session, include_completed=False)
        for existing in existing_tasks:
            existing_title = (existing.title or "").strip().casefold()
            if existing_title == normalized_title:
                if due_dt and existing.due_dt:
                    time_diff = abs((due_dt - existing.due_dt).total_seconds())
                    if time_diff < 3600:
                        LOGGER.warning("Duplicate task detected: %s", title)
                        return {
                            "task_id": existing.id,
                            "duplicate": True,
                            "message": "Bu görev zaten mevcut",
                        }
                if due_dt is None and existing.due_dt is None:
                    LOGGER.warning("Duplicate task detected without due date: %s", title)
                    return {
                        "task_id": existing.id,
                        "duplicate": True,
                        "message": "Bu görev zaten mevcut",
                    }

        task = Task(
            title=title or "Görev",
            due_dt=due_dt,
            priority=payload.get("priority", 0),
            tags=payload.get("tags"),
            notes=payload.get("notes"),
        )
        with get_session() as session:
            task = upsert_task(session, task)
        LOGGER.info("Task saved with id=%s", task.id)
        return {"task_id": task.id, "duplicate": False}

    def handle_update_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        task_id = int(payload.get("task_id", 0))
        with get_session() as session:
            task = session.get(Task, task_id)
            if task is None:
                LOGGER.warning("Task %s not found for update", task_id)
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
        LOGGER.info("Task %s updated with payload %s", task_id, payload)
        if hasattr(task, "model_dump"):
            payload = task.model_dump()  # type: ignore[attr-defined]
        else:
            payload = task.dict()
        return {"updated": True, "task": payload}

    def handle_complete_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        task_id = int(payload.get("task_id", 0))
        with get_session() as session:
            task = complete_task(session, task_id)
        if task is None:
            LOGGER.warning("Task %s could not be marked complete (not found)", task_id)
        else:
            LOGGER.info("Task %s marked as complete", task_id)
        return {"completed": task is not None}

    def handle_list_tasks(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        include_completed = payload.get("include_completed", False)
        with get_session() as session:
            tasks = list_tasks(session, include_completed=include_completed)
        LOGGER.info("Listing tasks include_completed=%s -> %d records", include_completed, len(tasks))
        return {
            "tasks": [
                {
                    "id": task.id,
                    "title": task.title,
                    "due_dt": task.due_dt.isoformat() if task.due_dt else None,
                    "status": task.status.value,
                    "notes": task.notes,
                    "priority": task.priority,
                    "tags": task.tags,
                    "created_at": task.created_at.isoformat(),
                    "updated_at": task.updated_at.isoformat(),
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


RELATIVE_TOKEN_PATTERN = re.compile(r"\{\s*(today|bugun|bugün|tomorrow|yarin|yarın)\s*\}", re.IGNORECASE)


def _normalise_relative_tokens(text: str) -> str:
    """Replace recognised relative date placeholders with ISO formatted dates."""

    def _replacement(match: re.Match[str]) -> str:
        token = match.group(1).lower()
        mapping = {
            "today": 0,
            "bugun": 0,
            "bugün": 0,
            "tomorrow": 1,
            "yarin": 1,
            "yarın": 1,
        }
        offset = mapping.get(token, 0)
        base = dt.datetime.now(tz=settings.timezone).date() + dt.timedelta(days=offset)
        return base.isoformat()

    return RELATIVE_TOKEN_PATTERN.sub(_replacement, text)


def _parse_iso(value: Any) -> Optional[dt.datetime]:
    if not value:
        return None
    if isinstance(value, dt.datetime):
        return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    text = _normalise_relative_tokens(text)
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


__all__ = ["ActionDispatcher", "ActionResult"]
