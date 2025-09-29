"""Placeholder for future tray UI implementation."""
from __future__ import annotations

import threading
from typing import Optional


class TrayController:
    """Minimal stub for pystray based system tray icon."""

    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:  # pragma: no cover - placeholder
        if self._thread and self._thread.is_alive():
            return
        # TODO: Implement pystray integration.

    def stop(self) -> None:  # pragma: no cover - placeholder
        # TODO: Stop tray thread when implemented.
        pass


__all__ = ["TrayController"]
