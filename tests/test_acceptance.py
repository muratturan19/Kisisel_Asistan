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
    monkeypatch.setattr(intent_module, "parse_datetime", lambda text, **_: fake_dt)

    action = intent_module.detect_intent("22'si 10:00 toplantı")
    app = get_app()
    result = app.service.handle_action(action)
    assert result["event_id"] is not None
    assert len(result["jobs"]) == 3

    storage = get_storage()
    with storage.get_session() as session:
        events = list(session.exec(select(storage.Event)))
    assert len(events) == 1
    assert "toplant" in events[0].title.lower()


def test_speech_style_event_command_is_listed():
    intent_module = __import__("mira_assistant.core.intent", fromlist=["handle", "Action"])
    dispatcher_module = __import__("mira_assistant.core.actions", fromlist=["ActionDispatcher"])

    action = intent_module.handle("yarın saat 10'da toplantı var")
    assert action is not None and action.intent == "add_event"

    dispatcher = dispatcher_module.ActionDispatcher()
    result = dispatcher.run(action)
    assert result.data["event_id"] is not None

    list_action = intent_module.Action(intent="list_events", payload={"range": "week"})
    events = dispatcher.run(list_action).data["events"]

    assert any(event["id"] == result.data["event_id"] for event in events)


def test_add_command_with_time_creates_event():
    intent_module = __import__("mira_assistant.core.intent", fromlist=["handle", "Action"])
    dispatcher_module = __import__("mira_assistant.core.actions", fromlist=["ActionDispatcher"])

    action = intent_module.handle("Yarın saat 16:00'da rapor teslimi ekle")
    assert action is not None and action.intent == "add_event"

    dispatcher = dispatcher_module.ActionDispatcher()
    result = dispatcher.run(action)
    assert result.data["event_id"] is not None

    upcoming_action = intent_module.Action(intent="list_events", payload={"range": "upcoming"})
    events = dispatcher.run(upcoming_action).data["events"]

    assert any(event["id"] == result.data["event_id"] for event in events)


def test_ingest_requires_document_context():
    intent_module = __import__("mira_assistant.core.intent", fromlist=["handle"])

    ingest_action = intent_module.handle("Belgeleri ekle")
    assert ingest_action is not None and ingest_action.intent == "ingest_docs"

    task_action = intent_module.handle("Yeni görev ekle")
    assert task_action is not None and task_action.intent == "add_task"


def test_upcoming_range_lists_future_events():
    dispatcher_module = __import__("mira_assistant.core.actions", fromlist=["ActionDispatcher"])
    intent_module = __import__("mira_assistant.core.intent", fromlist=["Action"])
    dispatcher = dispatcher_module.ActionDispatcher()

    far_future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=21)
    add_action = intent_module.Action(
        intent="add_event", payload={"title": "Uzak toplantı", "start": far_future.isoformat()}
    )
    result = dispatcher.run(add_action)
    assert result.data["event_id"] is not None

    upcoming_action = intent_module.Action(intent="list_events", payload={"range": "upcoming"})
    events = dispatcher.run(upcoming_action).data["events"]

    assert any(event["id"] == result.data["event_id"] for event in events)


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


def test_delete_event_clears_reminders():
    from mira_assistant.core.actions import ActionDispatcher
    from mira_assistant.core.scheduler import ReminderScheduler

    scheduler = ReminderScheduler()
    dispatcher = ActionDispatcher(scheduler=scheduler)
    future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=2)
    try:
        add_result = dispatcher.handle_add_event({"title": "Test", "start": future.isoformat()})
        event_id = add_result["event_id"]
        assert event_id is not None
        assert scheduler.list_jobs(), "Hatırlatma işi planlanamadı"

        delete_result = dispatcher.handle_delete_event({"event_id": event_id})
        assert delete_result["deleted"] is True
        assert scheduler.list_jobs() == []
    finally:
        scheduler.shutdown()


def test_note_intent_persists_note():
    app = get_app()
    service = app.service
    action_cls = __import__("mira_assistant.core.intent", fromlist=["Action"]).Action

    result = service.handle_action(action_cls(intent="note", payload={"text": "Market listesi: süt ve ekmek"}))
    assert result["saved"] is True
    assert result["note_id"] is not None

    storage = get_storage()
    with storage.get_session() as session:
        notes = list(session.exec(select(storage.Note)))
    assert len(notes) == 1
    assert "Market" in notes[0].title
