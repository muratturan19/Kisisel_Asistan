"""Speech-to-text interface placeholder."""
from __future__ import annotations

from typing import Protocol


class SpeechToText(Protocol):
    def transcribe(self, audio_path: str) -> str:
        ...


class MockSpeechToText:
    """Mock implementation returning static text."""

    def transcribe(self, audio_path: str) -> str:  # pragma: no cover - trivial
        return f"TODO: Transcribe {audio_path}"


__all__ = ["SpeechToText", "MockSpeechToText"]
