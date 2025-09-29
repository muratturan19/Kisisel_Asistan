"""Global configuration for Mira Assistant.

This module exposes runtime settings that read from environment variables while
providing sensible defaults that align with the technical design document.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from typing import List


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    """Container for application configuration."""

    timezone: str = os.getenv("MIRA_TZ", "Europe/Istanbul")
    reminder_minutes: List[int] = field(
        default_factory=lambda: json.loads(os.getenv("MIRA_REMINDERS", "[1440, 60, 10]"))
    )
    data_dir: Path = Path(os.getenv("MIRA_DATA_DIR", "~/MiraData")).expanduser()
    embed_model: str = os.getenv("MIRA_EMBED_MODEL", "multilingual-MiniLM")
    offline_only: bool = _bool_env("MIRA_OFFLINE_ONLY", True)
    ocr_enabled: bool = _bool_env("MIRA_OCR_ENABLED", True)

    def ensure_directories(self) -> None:
        """Ensure all required directories exist."""
        subdirs = [
            self.data_dir,
            self.data_dir / "inbox",
            self.data_dir / "archive",
            self.data_dir / "archive" / "by_topic",
            self.data_dir / "archive" / "by_type",
            self.data_dir / "audio",
            self.data_dir / "transcripts",
            self.data_dir / "summaries",
            self.data_dir / "db",
            self.data_dir / "logs",
        ]
        for subdir in subdirs:
            subdir.mkdir(parents=True, exist_ok=True)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "db" / "mira.sqlite"

    @property
    def vector_store_path(self) -> Path:
        return self.data_dir / "vector_store"

    @property
    def inbox_path(self) -> Path:
        return self.data_dir / "inbox"


settings = Settings()
