"""Text-to-speech helpers with edge-tts primary backend."""
from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Optional

LOGGER = logging.getLogger(__name__)


class SpeechSynthesizer:
    """Speak Turkish text using offline friendly backends."""

    def __init__(self) -> None:
        self._edge_voice = "tr-TR-ArdaNeural"
        self._edge_communicate = None
        self._pyttsx3_engine = None
        try:
            import edge_tts  # type: ignore

            self._edge_communicate = edge_tts.Communicate
        except Exception as exc:  # pragma: no cover - optional dependency
            LOGGER.warning("edge-tts unavailable: %s", exc)
            self._edge_communicate = None
            self._ensure_pyttsx3()

    def speak(self, text: str) -> None:
        if not text.strip():
            return
        if self._edge_communicate is not None:
            try:
                asyncio.run(self._speak_edge(text))
                return
            except RuntimeError:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(self._speak_edge(text))
                loop.close()
            except Exception as exc:  # pragma: no cover - fallback path
                LOGGER.error("edge-tts playback failed: %s", exc)
        self._speak_pyttsx3(text)

    async def _speak_edge(self, text: str) -> None:
        from config import settings

        communicator = self._edge_communicate(text, voice=self._edge_voice)
        output = Path(settings.audio_dir) / f"tts-{int(time.time())}.mp3"
        await communicator.save(str(output))
        if os.name == "nt":  # pragma: no cover - windows only
            try:
                os.startfile(str(output))  # type: ignore[attr-defined]
                return
            except Exception as exc:
                LOGGER.error("Windows playback failed: %s", exc)
        self._speak_pyttsx3(text)

    def _speak_pyttsx3(self, text: str) -> None:
        engine = self._ensure_pyttsx3()
        if engine is None:
            LOGGER.error("pyttsx3 not available to speak: %s", text)
            return
        engine.say(text)
        engine.runAndWait()

    def _ensure_pyttsx3(self):  # type: ignore[no-untyped-def]
        if self._pyttsx3_engine is None:
            try:
                import pyttsx3  # type: ignore

                engine = pyttsx3.init()
                engine.setProperty("voice", "tr")
                self._pyttsx3_engine = engine
            except Exception as exc:  # pragma: no cover - optional dependency
                LOGGER.error("pyttsx3 initialisation failed: %s", exc)
                self._pyttsx3_engine = None
        return self._pyttsx3_engine


__all__ = ["SpeechSynthesizer"]
