"""Text-to-speech interface placeholder."""
from __future__ import annotations

from typing import Protocol


class TextToSpeech(Protocol):
    def speak(self, text: str) -> None:
        ...


class MockTextToSpeech:
    """Mock implementation printing to stdout."""

    def speak(self, text: str) -> None:  # pragma: no cover - trivial
        print(f"[TTS] {text}")


__all__ = ["TextToSpeech", "MockTextToSpeech"]
