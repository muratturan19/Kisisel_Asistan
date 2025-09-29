"""Desktop notifications and optional speech output."""
from __future__ import annotations

import logging
from typing import Optional

from mira_assistant.io.tts import SpeechSynthesizer

LOGGER = logging.getLogger(__name__)

_try_toaster = None
_synthesizer: Optional[SpeechSynthesizer] = None


def _get_toaster():  # type: ignore[no-untyped-def]
    global _try_toaster
    if _try_toaster is not None:
        return _try_toaster
    try:
        from win10toast import ToastNotifier  # type: ignore

        _try_toaster = ToastNotifier()
    except Exception as exc:  # pragma: no cover - optional dependency
        LOGGER.warning("win10toast unavailable: %s", exc)
        _try_toaster = False
    return _try_toaster


def show_toast(title: str, message: str, *, duration: int = 5, speak: bool = False) -> None:
    toaster = _get_toaster()
    if toaster:
        try:
            toaster.show_toast(title, message, duration=duration, threaded=True)
        except Exception as exc:  # pragma: no cover - optional dependency
            LOGGER.error("Toast notification failed: %s", exc)
    else:
        LOGGER.info("Notification: %s - %s", title, message)
    if speak:
        _get_synthesizer().speak(message)


def _get_synthesizer() -> SpeechSynthesizer:
    global _synthesizer
    if _synthesizer is None:
        _synthesizer = SpeechSynthesizer()
    return _synthesizer


__all__ = ["show_toast"]
