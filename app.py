"""CLI entry point for Mira Assistant."""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

if sys.version_info >= (3, 13):  # pragma: no cover - defensive runtime guard
    raise RuntimeError(
        "Mira Assistant currently supports Python < 3.13. "
        "Some native dependencies (PyAV) do not yet provide wheels for Python 3.13."
    )

import typer
from rich.console import Console
from rich.table import Table
from sqlmodel import select

from config import settings
from mira_assistant.core.advisor import detect_conflicts
from mira_assistant.core.intent import Action, detect_intent
from mira_assistant.core.scheduler import ReminderScheduler
from mira_assistant.core.storage import (
    Chunk,
    Document,
    Event,
    Note,
    Task,
    add_event,
    add_note,
    get_session,
    init_db,
    list_due_tasks,
    upsert_task,
)
from mira_assistant.core.summarizer import summarise_topic
from mira_assistant.io.ingest import DocumentIngestor

console = Console()
cli = typer.Typer(help="Mira Assistant CLI", pretty_exceptions_show_locals=False)


class AssistantService:
    """High level orchestrator for intent handling."""

    def __init__(self, scheduler: Optional[ReminderScheduler] = None) -> None:
        self.scheduler = scheduler or ReminderScheduler()
        self._scheduler_started = False

    def start_scheduler(self) -> None:
        if not self._scheduler_started:
            self.scheduler.start()
            self._scheduler_started = True

    def shutdown(self) -> None:
        if self._scheduler_started:
            self.scheduler.shutdown()
            self._scheduler_started = False

    def handle_action(self, action: Action) -> Dict[str, Any]:
        handler = getattr(self, f"handle_{action.intent}", None)
        if handler is None:
            raise NotImplementedError(f"Intent {action.intent} not implemented")
        return handler(action.payload)

    def handle_add_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.start_scheduler()
        start_str = payload.get("start")
        if not start_str:
            raise ValueError("Event start time missing")
        start_dt = dt.datetime.fromisoformat(start_str)
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=dt.timezone.utc)
        event = Event(
            title=payload.get("title", "Etkinlik"),
            start_dt=start_dt,
            end_dt=payload.get("end_dt"),
            location=payload.get("location"),
            remind_policy=payload.get("remind_policy"),
            notes=payload.get("notes"),
        )
        with get_session() as session:
            event = add_event(session, event)
            warnings = detect_conflicts(session, event)
        reminder_minutes = (
            payload.get("remind_policy", {}).get("minutes_before") if payload.get("remind_policy") else None
        )
        job_ids = self.scheduler.schedule_event_reminders(event, reminder_minutes)
        return {"event_id": event.id, "warnings": warnings, "jobs": job_ids}

    def handle_add_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        due = payload.get("due")
        due_dt = dt.datetime.fromisoformat(due) if due else None
        task = Task(title=payload.get("title", "Görev"), due_dt=due_dt)
        with get_session() as session:
            task = upsert_task(session, task)
        return {"task_id": task.id}

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

    def handle_list_tasks(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        scope = payload.get("scope", "today")
        reference = dt.datetime.utcnow()
        with get_session() as session:
            tasks = list_due_tasks(session, reference)
        if scope == "today" and tasks:
            first_due = tasks[0].due_dt
            if first_due is not None:
                first_date = first_due.date()
                tasks = [task for task in tasks if task.due_dt and task.due_dt.date() == first_date]
        return {
            "scope": scope,
            "tasks": [
                {
                    "id": task.id,
                    "title": task.title,
                    "due_dt": task.due_dt.isoformat() if task.due_dt else None,
                    "status": task.status.value,
                }
                for task in tasks
            ],
        }

    def handle_summarize_topic(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        topic = payload["topic"]
        with get_session() as session:
            statement = select(Document).where(Document.topic == topic).order_by(Document.ingested_at.desc())
            documents = list(session.exec(statement))
            if not documents:
                summary = "- TODO: İlgili belge bulunamadı."
            else:
                chunk_texts: list[str] = []
                for document in documents:
                    chunks_stmt = select(Chunk).where(Chunk.doc_id == document.id).order_by(Chunk.seq)
                    doc_chunks = list(session.exec(chunks_stmt))
                    if doc_chunks:
                        chunk_texts.extend(chunk.text for chunk in doc_chunks)
                    else:
                        chunk_texts.append(Path(document.path).read_text(encoding="utf-8", errors="ignore"))
                summary = summarise_topic(chunk_texts)
        return {"topic": topic, "summary": summary}


service = AssistantService()


@cli.command("init-db")
def cli_init_db() -> None:
    """Initialise database and required directories."""
    settings.ensure_directories()
    init_db()
    console.print("Veritabanı hazır.")


@cli.command("ingest-doc")
def cli_ingest_doc(path: Path, topic: Optional[str] = None) -> None:
    """Ingest a document from the inbox."""
    ingestor = DocumentIngestor()
    result = ingestor.ingest(path, topic=topic)
    console.print(f"Belge eklendi: {result.document.title} -> {result.document.topic}")
    console.print(result.summary)


@cli.command("add-event")
def cli_add_event(title: str, start: str, reminder: Optional[str] = None) -> None:
    """Add an event with ISO start datetime."""
    remind_policy = None
    if reminder:
        remind_policy = {"minutes_before": [int(value) for value in reminder.split(",")]}
    action = Action(intent="add_event", payload={"title": title, "start": start, "remind_policy": remind_policy})
    result = service.handle_action(action)
    console.print(json.dumps(result, ensure_ascii=False, indent=2))


@cli.command("add-task")
def cli_add_task(title: str, due: Optional[str] = None) -> None:
    """Add a task with optional ISO due datetime."""
    action = Action(intent="add_task", payload={"title": title, "due": due})
    result = service.handle_action(action)
    console.print(json.dumps(result, ensure_ascii=False, indent=2))


@cli.command("list-tasks")
def cli_list_tasks() -> None:
    """List tasks due today or overdue."""
    action = Action(intent="list_tasks", payload={"scope": "today"})
    result = service.handle_action(action)
    table = Table(title="Görevler")
    table.add_column("ID")
    table.add_column("Başlık")
    table.add_column("Son Tarih")
    table.add_column("Durum")
    for task in result["tasks"]:
        table.add_row(str(task["id"]), task["title"] or "-", task["due_dt"] or "-", task["status"])
    console.print(table)


@cli.command("process")
def cli_process(text: str) -> None:
    """Process natural language command."""
    action = detect_intent(text)
    if action is None:
        console.print("Anlaşılamadı.")
        raise typer.Exit(code=1)
    result = service.handle_action(action)
    console.print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> None:
    settings.ensure_directories()
    cli()


if __name__ == "__main__":
    main()
