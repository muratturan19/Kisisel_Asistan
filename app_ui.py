"""Entry point for the Mira Assistant desktop application."""
from __future__ import annotations

import logging
import sys

from PySide6.QtCore import QMetaObject, Qt
from PySide6.QtWidgets import QApplication
from sqlmodel import select

from config import settings
from mira_assistant.core.storage import Event, get_session, init_db
from mira_assistant.ui.main_window import MainWindow
from mira_assistant.ui.tray import TrayController

if hasattr(sys.stdout, "reconfigure"):
    # Ensure console logging never crashes on characters that the active code
    # page cannot represent (e.g. combining Turkish dotted i variants).
    try:
        sys.stdout.reconfigure(errors="replace")
    except TypeError:
        # Some platforms expose ``reconfigure`` but do not accept the ``errors``
        # keyword – ignore silently and keep the default behaviour.
        pass

stream_handler = logging.StreamHandler(sys.stdout)
file_handler = logging.FileHandler(str(settings.log_dir / "mira.log"), encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    handlers=[file_handler, stream_handler],
)

LOGGER = logging.getLogger(__name__)


def create_app() -> tuple[QApplication, MainWindow, TrayController]:
    # Initialize the database (create tables if they don't exist)
    init_db()
    app = QApplication(sys.argv)
    window = MainWindow()
    scheduler = window.dispatcher.scheduler
    scheduler.start()
    with get_session() as session:
        events = list(session.exec(select(Event)))
    scheduler.restore_jobs_from_db(events)
    def invoke(name: str):
        return lambda: QMetaObject.invokeMethod(window, name, Qt.QueuedConnection)

    quit_app = lambda: QMetaObject.invokeMethod(app, "quit", Qt.QueuedConnection)
    tray = TrayController(
        on_toggle_listen=invoke("_toggle_listening"),
        on_show_agenda=invoke("refresh_events"),
        on_quick_note=invoke("quick_note"),
        on_quit=quit_app,
    )
    tray.start()
    return app, window, tray


def main() -> None:
    app, window, tray = create_app()
    window.show()
    exit_code = app.exec()
    tray.stop()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
