"""System tray integration using pystray."""
from __future__ import annotations

import threading
from typing import Callable, Optional

import pystray
from PIL import Image, ImageDraw


class TrayController:
    """Manage a pystray icon offering quick actions."""

    def __init__(
        self,
        *,
        on_toggle_listen: Callable[[], None],
        on_show_agenda: Callable[[], None],
        on_quick_note: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        self._on_toggle_listen = on_toggle_listen
        self._on_show_agenda = on_show_agenda
        self._on_quick_note = on_quick_note
        self._on_quit = on_quit
        self._icon: Optional[pystray.Icon] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._icon = pystray.Icon("Mira", self._build_image(), "Mira Assistant", menu=self._build_menu())
        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._icon:
            self._icon.stop()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)
        self._icon = None
        self._thread = None

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem("Dinlemeyi Başlat/Durdur", lambda icon: self._on_toggle_listen()),
            pystray.MenuItem("Bugünkü Ajanda", lambda icon: self._on_show_agenda()),
            pystray.MenuItem("Hızlı Not", lambda icon: self._on_quick_note()),
            pystray.MenuItem("Çıkış", lambda icon: self._on_quit()),
        )

    def _build_image(self) -> Image.Image:
        image = Image.new("RGB", (64, 64), "#2d2d2d")
        draw = ImageDraw.Draw(image)
        draw.ellipse((8, 8, 56, 56), outline="#00bcd4", width=4)
        draw.text((20, 22), "M", fill="#ffffff")
        return image


__all__ = ["TrayController"]
