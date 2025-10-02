"""Application configuration for Mira Assistant.

This module centralises directory paths, timezone configuration and model
selection so that the rest of the codebase can rely on a single source of
truth. Values are read from the environment when available but sensible
defaults matching the product brief are provided.  The defaults now place
the data directory inside the project tree to ensure that local development
environments always create the expected ``data/`` folder.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from typing import Iterable, List
from zoneinfo import ZoneInfo


BASE_DIR = Path(__file__).parent
DEFAULT_REMINDERS = [1440, 60, 10]
DEFAULT_DATA_DIR = BASE_DIR / "data"
DEFAULT_TIMEZONE = "Europe/Istanbul"
DEFAULT_EMBED_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_CHROMA_PATH = DEFAULT_DATA_DIR / "index"


def _load_int_list(value: str | None, fallback: Iterable[int]) -> List[int]:
    if not value:
        return list(fallback)
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list) and all(isinstance(item, int) for item in parsed):
            return list(parsed)
    except json.JSONDecodeError:
        pass
    return list(fallback)


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class Settings:
    """Runtime settings resolved from the environment."""

    data_dir: Path = Path(os.getenv("MIRA_DATA_DIR", str(DEFAULT_DATA_DIR))).expanduser()
    timezone_name: str = os.getenv("MIRA_TZ", DEFAULT_TIMEZONE)
    offline_only: bool = _bool_env("MIRA_OFFLINE_ONLY", True)
    default_reminders: List[int] = field(
        default_factory=lambda: _load_int_list(os.getenv("MIRA_REMINDERS"), DEFAULT_REMINDERS)
    )
    embed_model_name: str = os.getenv("MIRA_EMBED_MODEL", DEFAULT_EMBED_MODEL)
    chroma_path: Path = Path(os.getenv("MIRA_CHROMA_PATH", str(DEFAULT_CHROMA_PATH))).expanduser()

    def ensure_directories(self) -> None:
        """Create all folders required by the assistant if they do not exist."""

        paths = [
            self.data_dir,
            self.data_dir / "inbox",
            self.data_dir / "archive",
            self.data_dir / "archive" / "by_topic",
            self.data_dir / "audio",
            self.data_dir / "transcripts",
            self.data_dir / "summaries",
            self.data_dir / "db",
            self.log_dir,
            self.chroma_path,
        ]
        for path in paths:
            path.mkdir(parents=True, exist_ok=True)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "db" / "mira.sqlite"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)

    @property
    def inbox_path(self) -> Path:
        return self.data_dir / "inbox"

    @property
    def archive_root(self) -> Path:
        return self.data_dir / "archive" / "by_topic"

    @property
    def audio_dir(self) -> Path:
        return self.data_dir / "audio"

    @property
    def transcripts_dir(self) -> Path:
        return self.data_dir / "transcripts"

    @property
    def summaries_dir(self) -> Path:
        return self.data_dir / "summaries"


settings = Settings()
settings.ensure_directories()
