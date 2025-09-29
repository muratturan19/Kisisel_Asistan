import importlib
import sys
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def configure_env(tmp_path, monkeypatch):
    data_dir = tmp_path / "MiraData"
    monkeypatch.setenv("MIRA_DATA_DIR", str(data_dir))
    monkeypatch.setenv("MIRA_OFFLINE_ONLY", "true")
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    config = importlib.import_module("config")
    config.settings.data_dir = data_dir
    config.settings.ensure_directories()

    storage = importlib.import_module("mira_assistant.core.storage")
    storage._engine = None  # type: ignore[attr-defined]
    storage.init_db(config.settings.db_path)

    yield

    app_module = sys.modules.get("app")
    if app_module and hasattr(app_module, "service"):
        app_module.service.shutdown()
