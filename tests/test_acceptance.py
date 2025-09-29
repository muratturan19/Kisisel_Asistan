import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlmodel import select


def get_app():
    import importlib

    app = importlib.import_module("app")
    importlib.reload(app)
    return app


def get_storage():
    import importlib

    storage = importlib.import_module("mira_assistant.core.storage")
    return storage


def test_add_event_schedules_reminders(monkeypatch):
    import importlib

    intent_module = importlib.import_module("mira_assistant.core.intent")
    importlib.reload(intent_module)

    fake_dt = dt.datetime(2025, 10, 22, 10, 0, tzinfo=ZoneInfo("Europe/Istanbul"))
    monkeypatch.setattr(intent_module, "parse_datetime", lambda text: fake_dt)

    action = intent_module.detect_intent("22'si 10:00 toplantı")
    app = get_app()
    result = app.service.handle_action(action)
    assert result["event_id"] is not None
    assert len(result["jobs"]) == 3

    storage = get_storage()
    with storage.get_session() as session:
        events = list(session.exec(select(storage.Event)))
    assert len(events) == 1
    assert events[0].title.lower().startswith("toplant")


def test_ingest_document_moves_and_summarises(tmp_path):
    get_app()  # ensure directories initialised
    ingestor_module = __import__("mira_assistant.io.ingest", fromlist=["DocumentIngestor"])
    DocumentIngestor = ingestor_module.DocumentIngestor

    sample_file = tmp_path / "Fianca_rapor.txt"
    sample_file.write_text("Fianca projesi için rapor. Teslim tarihi 15 Mayıs.", encoding="utf-8")

    ingestor = DocumentIngestor()
    result = ingestor.ingest(sample_file)

    assert Path(result.document.path).exists()
    assert "Fianca" in result.document.topic
    assert result.summary.splitlines()[0].startswith("- Fianca")


def test_summarize_topic_returns_recent_summary(tmp_path):
    get_app()
    ingestor_module = __import__("mira_assistant.io.ingest", fromlist=["DocumentIngestor"])
    DocumentIngestor = ingestor_module.DocumentIngestor

    sample_file = tmp_path / "Fianca_notlar.txt"
    sample_file.write_text("Fianca toplantısı aksiyon: finans raporu hazırla.", encoding="utf-8")
    ingestor = DocumentIngestor()
    ingestor.ingest(sample_file, topic="Fianca")

    action = __import__("mira_assistant.core.intent", fromlist=["Action"]).Action(
        intent="summarize_topic", payload={"topic": "Fianca"}
    )
    result = get_app().service.handle_action(action)
    assert result["summary"].splitlines()[0].startswith("- Fianca")


def test_list_due_tasks_returns_today():
    app = get_app()
    now = dt.datetime(2025, 5, 1, 9, 0, tzinfo=dt.timezone.utc)

    action_cls = __import__("mira_assistant.core.intent", fromlist=["Action"]).Action
    service = app.service
    service.handle_action(action_cls(intent="add_task", payload={"title": "Raporu tamamla", "due": now.isoformat()}))
    future = now + dt.timedelta(days=2)
    service.handle_action(action_cls(intent="add_task", payload={"title": "Sunum hazırla", "due": future.isoformat()}))

    result = service.handle_action(action_cls(intent="list_tasks", payload={"scope": "today"}))
    assert len(result["tasks"]) == 1
    assert result["tasks"][0]["title"].startswith("Rapor")


def test_conflicting_events_produce_warning():
    app = get_app()
    service = app.service
    base_dt = dt.datetime(2025, 7, 1, 12, 0, tzinfo=ZoneInfo("Europe/Istanbul"))

    action_cls = __import__("mira_assistant.core.intent", fromlist=["Action"]).Action
    service.handle_action(action_cls(intent="add_event", payload={"title": "Ön görüşme", "start": base_dt.isoformat()}))
    result = service.handle_action(
        action_cls(
            intent="add_event",
            payload={"title": "Fianca toplantısı", "start": (base_dt + dt.timedelta(minutes=15)).isoformat()},
        )
    )
    assert result["warnings"], "Çakışma uyarısı bekleniyordu"
    assert "Çakışma" in result["warnings"][0]
