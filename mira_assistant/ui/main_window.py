"""PySide6 based desktop UI for Mira Assistant."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from mira_assistant.core.actions import ActionDispatcher
from mira_assistant.core.intent import Action, handle
from mira_assistant.io.stt import WhisperTranscriber

LOGGER = logging.getLogger(__name__)


class SpeechWorker(QThread):
    """Background worker capturing speech input."""

    transcribed = Signal(str)
    failed = Signal(str)

    def __init__(self, transcriber: WhisperTranscriber, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._transcriber = transcriber

    def run(self) -> None:  # pragma: no cover - requires microphone
        try:
            text = self._transcriber.listen_and_transcribe()
            if text:
                self.transcribed.emit(text)
        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    """Main application window binding UI to the action dispatcher."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Mira Asistanı")
        self.resize(960, 640)
        self.dispatcher = ActionDispatcher()
        self._transcriber: Optional[WhisperTranscriber] = None
        self._speech_worker: Optional[SpeechWorker] = None
        self._build_ui()
        self.refresh_lists()

    def _build_ui(self) -> None:
        container = QWidget(self)
        layout = QVBoxLayout(container)

        command_row = QHBoxLayout()
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("Komut yazın veya konuşun...")
        self.command_input.returnPressed.connect(self._on_command_entered)
        command_row.addWidget(self.command_input)

        self.listen_button = QPushButton("Konuş")
        self.listen_button.clicked.connect(self._toggle_listening)
        command_row.addWidget(self.listen_button)

        self.send_button = QPushButton("Gönder")
        self.send_button.clicked.connect(self._on_command_entered)
        command_row.addWidget(self.send_button)
        layout.addLayout(command_row)

        self.tabs = QTabWidget()
        self._agenda_tab = self._build_agenda_tab()
        self._tasks_tab = self._build_tasks_tab()
        self._knowledge_tab = self._build_knowledge_tab()
        self.tabs.addTab(self._agenda_tab, "Ajanda")
        self.tabs.addTab(self._tasks_tab, "Görevler")
        self.tabs.addTab(self._knowledge_tab, "Konu & Arşiv")
        layout.addWidget(self.tabs)

        self.status_label = QLabel("Hazır")
        layout.addWidget(self.status_label)

        container.setLayout(layout)
        self.setCentralWidget(container)

    def _build_agenda_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.event_list = QListWidget()
        layout.addWidget(self.event_list)
        refresh_btn = QPushButton("Ajandayı Yenile")
        refresh_btn.clicked.connect(self.refresh_events)
        layout.addWidget(refresh_btn)
        return widget

    def _build_tasks_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.task_list = QListWidget()
        layout.addWidget(self.task_list)
        refresh_btn = QPushButton("Görevleri Yenile")
        refresh_btn.clicked.connect(self.refresh_tasks)
        layout.addWidget(refresh_btn)
        return widget

    def _build_knowledge_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.topic_input = QLineEdit()
        self.topic_input.setPlaceholderText("Konu")
        layout.addWidget(self.topic_input)
        ingest_row = QHBoxLayout()
        ingest_btn = QPushButton("Inbox'u Tara")
        ingest_btn.clicked.connect(self._ingest_inbox)
        ingest_row.addWidget(ingest_btn)
        file_btn = QPushButton("Dosya Seç")
        file_btn.clicked.connect(self._ingest_file)
        ingest_row.addWidget(file_btn)
        layout.addLayout(ingest_row)

        self.summary_view = QTextEdit()
        self.summary_view.setReadOnly(True)
        layout.addWidget(self.summary_view)

        summarize_btn = QPushButton("Konu Özetle")
        summarize_btn.clicked.connect(self._summarize_topic)
        layout.addWidget(summarize_btn)
        return widget

    def _on_command_entered(self) -> None:
        text = self.command_input.text().strip()
        if not text:
            return
        action = handle(text)
        if action is None:
            self.status_label.setText("Komut anlaşılamadı.")
            return
        self._execute_action(action)
        self.command_input.clear()

    def _execute_action(self, action: Optional[Action]) -> None:
        if action is None:
            return
        try:
            result = self.dispatcher.run(action)
            self.status_label.setText(f"{action.intent} işlendi.")
            LOGGER.info("Action result: %s", result.data)
        except Exception as exc:
            LOGGER.exception("Komut çalıştırma hatası: %s", exc)
            QMessageBox.critical(self, "Hata", str(exc))
            return
        self.refresh_lists()
        if action.intent == "summarize_topic":
            summary = result.data.get("summary", "")
            self.summary_view.setPlainText(summary)

    @Slot()
    def refresh_lists(self) -> None:
        self.refresh_events()
        self.refresh_tasks()

    @Slot()
    def refresh_events(self) -> None:
        action = Action(intent="list_events", payload={"range": "today"})
        result = self.dispatcher.run(action)
        self.event_list.clear()
        for event in result.data.get("events", []):
            start = event.get("start_dt", "")
            title = event.get("title", "")
            item = QListWidgetItem(f"{start} - {title}")
            self.event_list.addItem(item)

    @Slot()
    def refresh_tasks(self) -> None:
        action = Action(intent="list_tasks", payload={"include_completed": False})
        result = self.dispatcher.run(action)
        self.task_list.clear()
        for task in result.data.get("tasks", []):
            due = task.get("due_dt") or "-"
            status = task.get("status")
            title = task.get("title")
            item = QListWidgetItem(f"[{status}] {title} (Son: {due})")
            self.task_list.addItem(item)

    @Slot()
    def _toggle_listening(self) -> None:
        if self._speech_worker and self._speech_worker.isRunning():
            self._speech_worker.terminate()
            self._speech_worker = None
            self.status_label.setText("Dinleme durduruldu.")
            return
        if self._transcriber is None:
            self._transcriber = WhisperTranscriber()
        self._speech_worker = SpeechWorker(self._transcriber, self)
        self._speech_worker.transcribed.connect(self._on_transcribed)
        self._speech_worker.failed.connect(self._on_speech_failed)
        self._speech_worker.start()
        self.status_label.setText("Dinleniyor...")

    @Slot(str)
    def _on_transcribed(self, text: str) -> None:
        self.status_label.setText(f"Algılanan komut: {text}")
        action = handle(text)
        self._execute_action(action)

    @Slot(str)
    def _on_speech_failed(self, error: str) -> None:
        QMessageBox.warning(self, "STT Hatası", error)
        self.status_label.setText("Dinleme başarısız.")

    @Slot()
    def _ingest_inbox(self) -> None:
        topic = self.topic_input.text().strip() or None
        action = Action(intent="ingest_docs", payload={"topic": topic})
        result = self.dispatcher.run(action)
        titles = ", ".join(result.data.get("ingested", []))
        self.status_label.setText(f"Arşive alınan: {titles}" if titles else "Yeni belge yok.")

    @Slot()
    def _ingest_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Belge Seç", str(Path.home()))
        if not file_path:
            return
        topic = self.topic_input.text().strip() or None
        try:
            result = self.dispatcher.ingestor.ingest(Path(file_path), topic=topic)
        except Exception as exc:
            QMessageBox.critical(self, "İşleme hatası", str(exc))
            return
        self.status_label.setText(f"Belge işlendi: {result.document.title if result.document else '—'}")

    @Slot()
    def _summarize_topic(self) -> None:
        topic = self.topic_input.text().strip()
        if not topic:
            QMessageBox.information(self, "Bilgi", "Özet için konu girin.")
            return
        action = Action(intent="summarize_topic", payload={"topic": topic})
        result = self.dispatcher.run(action)
        summary = result.data.get("summary", "")
        self.summary_view.setPlainText(summary)

    @Slot()
    def quick_note(self) -> None:
        text, accepted = QInputDialog.getText(self, "Hızlı Not", "Not içeriği:")
        if not accepted or not text.strip():
            return
        action = Action(intent="add_task", payload={"title": text.strip()})
        self._execute_action(action)


__all__ = ["MainWindow"]
