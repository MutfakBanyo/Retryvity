"""A tiny, dependency-free JSON settings store.

Deliberately not QSettings: keeping this Qt-free lets it be unit tested
without PySide6 and keeps the storage format human-readable/auditable.
Only non-sensitive UI/developer preferences are stored here — never
credentials or scene data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from corona_doctor.core.constants import ORG_NAME, SETTINGS_NAMESPACE

DEFAULT_SETTINGS: dict[str, Any] = {
    "theme": "dark",
    "ui_performance_mode": False,
    "developer_mode": False,
    "last_nav_section": "overview",
    "dock_state": None,
}


def default_settings_path() -> Path:
    import os

    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path.home() / ".config"
    return base / ORG_NAME / f"{SETTINGS_NAMESPACE}.json"


class SettingsStore:
    """Reads/writes a small JSON document of user preferences."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or default_settings_path()
        self._data: dict[str, Any] = dict(DEFAULT_SETTINGS)
        self.load()

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> None:
        if not self._path.exists():
            return
        try:
            with self._path.open("r", encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                self._data.update(loaded)
        except (OSError, json.JSONDecodeError):
            # Corrupt or unreadable settings must never block startup.
            pass

    def save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2, sort_keys=True)
        except OSError:
            pass

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def as_dict(self) -> dict[str, Any]:
        return dict(self._data)
