# -*- coding: utf-8 -*-

"""PySide6 based desktop UI for Mira Assistant with modern layout."""
from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path
from typing import Dict, Optional

from PySide6.QtCore import QThread, Qt, Signal, Slot, QTimer, QSize
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QCheckBox,
    QFrame,
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
        except Exception as exc:  # pragma: no cover - requires microphone
            self.failed.emit(str(exc))


class ModernButton(QPushButton):
    """Button with Mira Assistant's modern styling."""

    def __init__(self, text: str, *, primary: bool = False, parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.primary = primary
        self.setMinimumHeight(40)
        self.setCursor(Qt.PointingHandCursor)
        self.update_style()

    def update_style(self) -> None:
        if self.primary:
            self.setStyleSheet(
                """
                QPushButton {
                    background-color: #1E88E5;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    padding: 8px 24px;
                    font-weight: 600;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #1976D2;
                }
                QPushButton:pressed {
                    background-color: #1565C0;
                }
                """
            )
        else:
            self.setStyleSheet(
                """
                QPushButton {
                    background-color: transparent;
                    color: #1E88E5;
                    border: 2px solid #1E88E5;
                    border-radius: 8px;
                    padding: 8px 24px;
                    font-weight: 600;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: rgba(30, 136, 229, 0.1);
                }
                QPushButton:pressed {
                    background-color: rgba(30, 136, 229, 0.2);
                }
                """
            )


class FeedbackLabel(QLabel):
    """Transient success/error banner shown underneath the command box."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(40)
        self.setAlignment(Qt.AlignCenter)
        self.hide()

    def show_success(self, message: str) -> None:
        self.setStyleSheet(
            """
            QLabel {
                background-color: #4CAF50;
                color: white;
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: 500;
            }
            """
        )
        self.setText(f"✓ {message}")
        self.show()
        QTimer.singleShot(3000, self.hide)

    def show_error(self, message: str) -> None:
        self.setStyleSheet(
            """
            QLabel {
                background-color: #F44336;
                color: white;
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: 500;
            }
            """
        )
        self.setText(f"⚠ {message}")
        self.show()
        QTimer.singleShot(3000, self.hide)


class MainWindow(QMainWindow):
    """Main application window binding the modern UI with assistant services."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Mira Asistan")
        self.setMinimumSize(1200, 700)

        self.dispatcher = ActionDispatcher()
        self._transcriber: Optional[WhisperTranscriber] = None
        self._speech_worker: Optional[SpeechWorker] = None

        self.is_dark_theme = False
        self.mic_active = False
        self._summary_labels: Dict[str, QLabel] = {}
        self._tasks: list[dict] = []
        self._events: list[dict] = []

        self._build_ui()
        self.apply_light_theme()
        self.refresh_lists()

    def _build_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._create_app_bar(main_layout)

        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self._create_nav_menu(content_layout)

        splitter = QSplitter(Qt.Horizontal)
        self._create_command_panel(splitter)
        self._create_right_panel(splitter)
        splitter.setSizes([600, 400])
        splitter.setHandleWidth(1)

        content_layout.addWidget(splitter)
        main_layout.addLayout(content_layout)

    def _create_app_bar(self, parent_layout: QVBoxLayout) -> None:
        appbar = QWidget()
        appbar.setObjectName("appBar")
        appbar.setMinimumHeight(56)
        appbar.setMaximumHeight(56)

        layout = QHBoxLayout(appbar)
        layout.setContentsMargins(16, 0, 16, 0)

        logo_label = QLabel("🎯")
        logo_label.setFont(QFont("Segoe UI", 20))
        layout.addWidget(logo_label)

        title_label = QLabel("Mira Asistan")
        title_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        layout.addWidget(title_label, 1, Qt.AlignCenter)

        self.theme_btn = QPushButton("🌙")
        self.theme_btn.setFixedSize(40, 40)
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self.theme_btn.clicked.connect(self.toggle_theme)

        settings_btn = QPushButton("⚙")
        settings_btn.setFixedSize(40, 40)
        settings_btn.setCursor(Qt.PointingHandCursor)
        settings_btn.clicked.connect(self._show_settings_placeholder)

        about_btn = QPushButton("ℹ")
        about_btn.setFixedSize(40, 40)
        about_btn.setCursor(Qt.PointingHandCursor)
        about_btn.clicked.connect(self._show_about_placeholder)

        layout.addWidget(self.theme_btn)
        layout.addWidget(settings_btn)
        layout.addWidget(about_btn)

        parent_layout.addWidget(appbar)

    def _create_nav_menu(self, parent_layout: QHBoxLayout) -> None:
        nav_widget = QWidget()
        nav_widget.setObjectName("navMenu")
        nav_widget.setMinimumWidth(220)
        nav_widget.setMaximumWidth(220)

        nav_layout = QVBoxLayout(nav_widget)
        nav_layout.setContentsMargins(8, 16, 8, 16)
        nav_layout.setSpacing(8)

        self.nav_list = QListWidget()
        self.nav_list.setObjectName("navList")
        for icon, text in [("📅", "Takvim"), ("✓", "Yapılacaklar"), ("👥", "Toplantılar"), ("⭐", "Önemliler")]:
            item = QListWidgetItem(f"{icon}  {text}")
            item.setSizeHint(QSize(200, 48))
            self.nav_list.addItem(item)
        self.nav_list.setCurrentRow(0)
        self.nav_list.currentRowChanged.connect(self._on_nav_changed)

        nav_layout.addWidget(self.nav_list)
        nav_layout.addStretch()

        parent_layout.addWidget(nav_widget)

    def _create_command_panel(self, splitter: QSplitter) -> None:
        command_widget = QWidget()
        command_widget.setObjectName("commandPanel")
        command_layout = QVBoxLayout(command_widget)
        command_layout.setContentsMargins(24, 24, 24, 24)
        command_layout.setSpacing(16)

        title = QLabel("Komut Merkezi")
        title.setFont(QFont("Segoe UI", 18, QFont.Bold))
        command_layout.addWidget(title)

        self.command_input = QPlainTextEdit()
        self.command_input.setObjectName("commandText")
        self.command_input.setPlaceholderText(
            "Örnek: '22'si saat 10:00'da tedarikçi toplantısı'\nveya 'Yarın saat 16:00'da rapor teslimi ekle'"
        )
        self.command_input.setMinimumHeight(120)
        command_layout.addWidget(self.command_input)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)

        self.save_btn = ModernButton("Kaydet", primary=True)
        self.save_btn.setObjectName("btnSaveCommand")
        self.save_btn.clicked.connect(self.handle_save_command)

        self.mic_btn = ModernButton("🎤 Konuş", primary=False)
        self.mic_btn.setObjectName("btnMicToggle")
        self.mic_btn.clicked.connect(self._toggle_listening)

        button_layout.addWidget(self.save_btn)
        button_layout.addWidget(self.mic_btn)
        button_layout.addStretch()

        command_layout.addLayout(button_layout)

        self.feedback_label = FeedbackLabel()
        command_layout.addWidget(self.feedback_label)

        summary_frame = QFrame()
        summary_frame.setObjectName("summaryCard")
        summary_layout = QVBoxLayout(summary_frame)
        summary_layout.setContentsMargins(16, 16, 16, 16)

        summary_title = QLabel("📊 Özet")
        summary_title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        summary_layout.addWidget(summary_title)

        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(12)

        summaries = [
            ("today", "Bugün"),
            ("week", "Bu hafta"),
            ("pending", "Bekleyen"),
        ]
        for key, label in summaries:
            stat_widget = QWidget()
            stat_layout = QVBoxLayout(stat_widget)
            stat_layout.setContentsMargins(8, 8, 8, 8)

            stat_value = QLabel("-")
            stat_value.setFont(QFont("Segoe UI", 16, QFont.Bold))
            stat_value.setAlignment(Qt.AlignCenter)
            self._summary_labels[key] = stat_value

            stat_label = QLabel(label)
            stat_label.setAlignment(Qt.AlignCenter)

            stat_layout.addWidget(stat_value)
            stat_layout.addWidget(stat_label)
            stats_layout.addWidget(stat_widget)

        summary_layout.addLayout(stats_layout)
        command_layout.addWidget(summary_frame)
        command_layout.addStretch()

        splitter.addWidget(command_widget)

    def _create_right_panel(self, splitter: QSplitter) -> None:
        right_widget = QWidget()
        right_widget.setObjectName("rightPanel")
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        right_splitter = QSplitter(Qt.Vertical)
        self._create_todo_list(right_splitter)
        self._create_meetings_list(right_splitter)
        right_splitter.setSizes([350, 350])

        right_layout.addWidget(right_splitter)
        splitter.addWidget(right_widget)

    def _create_todo_list(self, splitter: QSplitter) -> None:
        todo_widget = QWidget()
        todo_layout = QVBoxLayout(todo_widget)
        todo_layout.setContentsMargins(16, 16, 16, 16)
        todo_layout.setSpacing(12)

        todo_title = QLabel("✓ Yapılacaklar")
        todo_title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        todo_layout.addWidget(todo_title)

        self.todo_table = QTableWidget()
        self.todo_table.setObjectName("tableTodos")
        self.todo_table.setColumnCount(4)
        self.todo_table.setHorizontalHeaderLabels(["✓", "Görev", "Tarih", "Durum"])
        self.todo_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.todo_table.setColumnWidth(0, 40)
        self.todo_table.setColumnWidth(2, 120)
        self.todo_table.setColumnWidth(3, 90)
        self.todo_table.verticalHeader().setVisible(False)
        self.todo_table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        todo_layout.addWidget(self.todo_table)
        splitter.addWidget(todo_widget)

    def _create_meetings_list(self, splitter: QSplitter) -> None:
        meetings_widget = QWidget()
        meetings_layout = QVBoxLayout(meetings_widget)
        meetings_layout.setContentsMargins(16, 16, 16, 16)
        meetings_layout.setSpacing(12)

        meetings_title = QLabel("📅 Yaklaşan Toplantılar")
        meetings_title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        meetings_layout.addWidget(meetings_title)

        self.meetings_table = QTableWidget()
        self.meetings_table.setObjectName("tableAgenda")
        self.meetings_table.setColumnCount(4)
        self.meetings_table.setHorizontalHeaderLabels(["Tarih", "Saat", "Başlık", "Konum"])
        self.meetings_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.meetings_table.setColumnWidth(0, 90)
        self.meetings_table.setColumnWidth(1, 70)
        self.meetings_table.setColumnWidth(3, 120)
        self.meetings_table.verticalHeader().setVisible(False)
        self.meetings_table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        meetings_layout.addWidget(self.meetings_table)
        splitter.addWidget(meetings_widget)

    @Slot()
    def handle_save_command(self) -> None:
        command_text = self.command_input.toPlainText().strip()
        if not command_text:
            self.feedback_label.show_error("Lütfen bir komut girin!")
            return
        action = handle(command_text)
        if action is None:
            self.feedback_label.show_error("Komut anlaşılamadı.")
            return
        self._execute_action(action)
        self.command_input.clear()

    def _execute_action(self, action: Optional[Action]) -> None:
        if action is None:
            return
        try:
            result = self.dispatcher.run(action)
        except Exception as exc:  # pragma: no cover - UI feedback
            LOGGER.exception("Komut çalıştırma hatası: %s", exc)
            self.feedback_label.show_error(str(exc))
            QMessageBox.critical(self, "Hata", str(exc))
            return

        intent_text = {
            "add_event": "Etkinlik kaydedildi",
            "add_task": "Görev kaydedildi",
            "complete_task": "Görev tamamlandı",
            "schedule_reminder": "Hatırlatma planlandı",
            "ingest_docs": "Belgeler işlendi",
            "summarize_topic": "Özet hazır",
        }.get(action.intent, "Komut başarıyla işlendi")
        self.feedback_label.show_success(intent_text)
        self.refresh_lists()

        if action.intent == "summarize_topic":
            summary = result.data.get("summary", "")
            self._show_summary(summary)

    def _show_summary(self, text: str) -> None:
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Özet")
        dialog.setText(text or "Özet bulunamadı.")
        dialog.exec()

    @Slot()
    def refresh_lists(self) -> None:
        self.refresh_events()
        self.refresh_tasks()

    @Slot()
    def refresh_events(self) -> None:
        action = Action(intent="list_events", payload={"range": "upcoming"})
        result = self.dispatcher.run(action)
        self._events = result.data.get("events", [])
        self.meetings_table.setRowCount(len(self._events))
        for row, event in enumerate(self._events):
            start_dt = self._parse_iso(event.get("start_dt"))
            date_text = start_dt.strftime("%d.%m") if start_dt else "-"
            time_text = start_dt.strftime("%H:%M") if start_dt else "-"
            title = event.get("title") or "-"
            location = event.get("location") or "-"

            self.meetings_table.setItem(row, 0, QTableWidgetItem(date_text))
            self.meetings_table.setItem(row, 1, QTableWidgetItem(time_text))
            self.meetings_table.setItem(row, 2, QTableWidgetItem(title))
            self.meetings_table.setItem(row, 3, QTableWidgetItem(location))

        self._update_summary_stats()

    @Slot()
    def refresh_tasks(self) -> None:
        action = Action(intent="list_tasks", payload={"include_completed": False})
        result = self.dispatcher.run(action)
        self._tasks = result.data.get("tasks", [])
        self.todo_table.setRowCount(len(self._tasks))

        for row, task in enumerate(self._tasks):
            checkbox = QCheckBox()
            checkbox.setCursor(Qt.PointingHandCursor)
            status = task.get("status", "pending")
            checkbox.setChecked(status == "done")
            checkbox.stateChanged.connect(
                lambda state, task_id=task.get("id"): self._on_task_checkbox_changed(task_id, state == Qt.Checked)
            )
            checkbox_widget = QWidget()
            checkbox_layout = QHBoxLayout(checkbox_widget)
            checkbox_layout.addWidget(checkbox)
            checkbox_layout.setAlignment(Qt.AlignCenter)
            checkbox_layout.setContentsMargins(0, 0, 0, 0)
            self.todo_table.setCellWidget(row, 0, checkbox_widget)

            title_item = QTableWidgetItem(task.get("title") or "-")
            self.todo_table.setItem(row, 1, title_item)

            due_text = self._format_datetime(task.get("due_dt"))
            self.todo_table.setItem(row, 2, QTableWidgetItem(due_text))

            status_item = QTableWidgetItem(status.capitalize())
            if status == "done":
                status_item.setForeground(QColor("#4CAF50"))
            else:
                status_item.setForeground(QColor("#F44336"))
            self.todo_table.setItem(row, 3, status_item)

        self._update_summary_stats()

    def _on_task_checkbox_changed(self, task_id: Optional[int], checked: bool) -> None:
        if task_id is None:
            return
        if checked:
            action = Action(intent="complete_task", payload={"task_id": task_id})
            self._execute_action(action)
        else:
            # undo is not supported, revert checkbox via refresh
            self.feedback_label.show_error("Görev yeniden açma desteklenmiyor.")
            self.refresh_tasks()

    def _update_summary_stats(self) -> None:
        today = dt.date.today()
        today_tasks = 0
        pending_tasks = 0
        now_utc = dt.datetime.now(dt.timezone.utc)
        week_later = now_utc + dt.timedelta(days=7)
        week_events = 0
        for task in self._tasks:
            status = task.get("status")
            if status != "done":
                pending_tasks += 1
            due = self._parse_iso(task.get("due_dt"))
            if due and due.date() == today and status != "done":
                today_tasks += 1

        for event in self._events:
            start = self._parse_iso(event.get("start_dt"))
            if start and now_utc <= start <= week_later:
                week_events += 1

        if label := self._summary_labels.get("today"):
            label.setText(f"{today_tasks} görev")
        if label := self._summary_labels.get("week"):
            label.setText(f"{week_events} toplantı")
        if label := self._summary_labels.get("pending"):
            label.setText(f"{pending_tasks}")

    def _format_datetime(self, value: Optional[str]) -> str:
        parsed = self._parse_iso(value)
        if parsed is None:
            return "-"
        local = parsed.astimezone()
        return local.strftime("%d.%m %H:%M")

    @staticmethod
    def _parse_iso(value: Optional[str]) -> Optional[dt.datetime]:
        if not value:
            return None
        text = str(value).replace("Z", "+00:00")
        try:
            parsed = dt.datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed

    @Slot()
    def _toggle_listening(self) -> None:
        if self._speech_worker and self._speech_worker.isRunning():
            self._speech_worker.terminate()
            self._speech_worker = None
            self.mic_active = False
            self.mic_btn.setText("🎤 Konuş")
            self.mic_btn.primary = False
            self.mic_btn.update_style()
            self.feedback_label.hide()
            return

        if self._transcriber is None:
            self._transcriber = WhisperTranscriber()

        self._speech_worker = SpeechWorker(self._transcriber, self)
        self._speech_worker.transcribed.connect(self._on_transcribed)
        self._speech_worker.failed.connect(self._on_speech_failed)
        self._speech_worker.start()

        self.mic_active = True
        self.mic_btn.setText("⏹ Durdur")
        self.mic_btn.primary = True
        self.mic_btn.update_style()
        self.feedback_label.setStyleSheet(
            """
            QLabel {
                background-color: #1E88E5;
                color: white;
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: 500;
            }
            """
        )
        self.feedback_label.setText("🎤 Dinleniyor...")
        self.feedback_label.show()

    @Slot(str)
    def _on_transcribed(self, text: str) -> None:
        self.mic_btn.setText("🎤 Konuş")
        self.mic_btn.primary = False
        self.mic_btn.update_style()
        self.feedback_label.show_success(f"Algılanan komut: {text}")
        self.mic_active = False

        action = handle(text)
        self._execute_action(action)

    @Slot(str)
    def _on_speech_failed(self, error: str) -> None:
        self.feedback_label.show_error(error)
        QMessageBox.warning(self, "STT Hatası", error)
        self.mic_btn.setText("🎤 Konuş")
        self.mic_btn.primary = False
        self.mic_btn.update_style()
        self.mic_active = False

    def toggle_theme(self) -> None:
        self.is_dark_theme = not self.is_dark_theme
        if self.is_dark_theme:
            self.apply_dark_theme()
            self.theme_btn.setText("☀")
        else:
            self.apply_light_theme()
            self.theme_btn.setText("🌙")

    def apply_light_theme(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background-color: #F7F9FC;
            }
            QWidget#appBar {
                background-color: #FFFFFF;
                border-bottom: 1px solid #E5E7EB;
            }
            QWidget#navMenu {
                background-color: #FFFFFF;
                border-right: 1px solid #E5E7EB;
            }
            QListWidget#navList {
                background-color: transparent;
                border: none;
                outline: none;
                font-size: 14px;
                font-weight: 500;
            }
            QListWidget#navList::item {
                border-radius: 8px;
                padding: 8px;
                margin: 2px 0px;
                color: #0F172A;
            }
            QListWidget#navList::item:selected {
                background-color: #E3F2FD;
                color: #1E88E5;
            }
            QListWidget#navList::item:hover {
                background-color: #F5F5F5;
            }
            QWidget#commandPanel {
                background-color: #F7F9FC;
            }
            QWidget#rightPanel {
                background-color: #FFFFFF;
                border-left: 1px solid #E5E7EB;
            }
            QPlainTextEdit#commandText {
                background-color: #FFFFFF;
                border: 2px solid #E5E7EB;
                border-radius: 8px;
                padding: 12px;
                font-size: 14px;
                color: #0F172A;
            }
            QPlainTextEdit#commandText:focus {
                border: 2px solid #1E88E5;
            }
            QFrame#summaryCard {
                background-color: #FFFFFF;
                border-radius: 12px;
                border: 1px solid #E5E7EB;
            }
            QTableWidget {
                background-color: #FFFFFF;
                border: none;
                gridline-color: #E5E7EB;
                font-size: 13px;
            }
            QTableWidget::item {
                padding: 8px;
                color: #0F172A;
            }
            QHeaderView::section {
                background-color: #F7F9FC;
                padding: 8px;
                border: none;
                border-bottom: 2px solid #E5E7EB;
                font-weight: 600;
                color: #64748B;
            }
            QPushButton {
                border-radius: 8px;
                font-weight: 500;
            }
            QLabel {
                color: #0F172A;
            }
        """
        )

    def apply_dark_theme(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background-color: #0B1220;
            }
            QWidget#appBar {
                background-color: #111827;
                border-bottom: 1px solid #374151;
            }
            QWidget#navMenu {
                background-color: #111827;
                border-right: 1px solid #374151;
            }
            QListWidget#navList {
                background-color: transparent;
                border: none;
                outline: none;
                font-size: 14px;
                font-weight: 500;
            }
            QListWidget#navList::item {
                border-radius: 8px;
                padding: 8px;
                margin: 2px 0px;
                color: #E5E7EB;
            }
            QListWidget#navList::item:selected {
                background-color: #1E3A5F;
                color: #60A5FA;
            }
            QListWidget#navList::item:hover {
                background-color: #1F2937;
            }
            QWidget#commandPanel {
                background-color: #0B1220;
            }
            QWidget#rightPanel {
                background-color: #111827;
                border-left: 1px solid #374151;
            }
            QPlainTextEdit#commandText {
                background-color: #1F2937;
                border: 2px solid #374151;
                border-radius: 8px;
                padding: 12px;
                font-size: 14px;
                color: #E5E7EB;
            }
            QPlainTextEdit#commandText:focus {
                border: 2px solid #60A5FA;
            }
            QFrame#summaryCard {
                background-color: #111827;
                border-radius: 12px;
                border: 1px solid #374151;
            }
            QTableWidget {
                background-color: #111827;
                border: none;
                gridline-color: #374151;
                font-size: 13px;
            }
            QTableWidget::item {
                padding: 8px;
                color: #E5E7EB;
            }
            QHeaderView::section {
                background-color: #1F2937;
                padding: 8px;
                border: none;
                border-bottom: 2px solid #374151;
                font-weight: 600;
                color: #9CA3AF;
            }
            QPushButton {
                border-radius: 8px;
                font-weight: 500;
            }
            QLabel {
                color: #E5E7EB;
            }
        """
        )

    def _show_settings_placeholder(self) -> None:
        QMessageBox.information(self, "Ayarlar", "Ayarlar yakında eklenecek.")

    def _show_about_placeholder(self) -> None:
        QMessageBox.information(self, "Mira Asistan", "Mira Asistan masaüstü uygulaması.")

    def _on_nav_changed(self, index: int) -> None:
        if index == 0:
            self.refresh_events()
        elif index == 1:
            self.refresh_tasks()
        elif index == 2:
            self.refresh_events()
        else:
            self.refresh_lists()

    @Slot()
    def quick_note(self) -> None:
        text, accepted = QInputDialog.getText(self, "Hızlı Not", "Not içeriği:")
        if not accepted or not text.strip():
            return
        action = Action(intent="add_task", payload={"title": text.strip()})
        self._execute_action(action)

    @Slot()
    def _ingest_inbox(self) -> None:
        action = Action(intent="ingest_docs", payload={"topic": None})
        self._execute_action(action)

    @Slot()
    def _ingest_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Belge Seç", str(Path.home()))
        if not file_path:
            return
        try:
            result = self.dispatcher.ingestor.ingest(Path(file_path))
        except Exception as exc:  # pragma: no cover - UI feedback
            LOGGER.exception("Belge işlenemedi: %s", exc)
            QMessageBox.critical(self, "İşleme hatası", str(exc))
            return
        title = result.document.title if result.document else Path(file_path).name
        self.feedback_label.show_success(f"Belge işlendi: {title}")


__all__ = ["MainWindow"]
