"""Small JSON settings store used before the Qt QSettings adapter is added."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import RLock
from typing import Any, Mapping


class SettingsStore:
    """Persist non-secret application settings atomically.

    Passwords and private key contents deliberately do not belong here. The
    connection profile only stores a reference to an operating-system keyring
    entry; a future Qt adapter can use the same contract.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path).expanduser()
        self._lock = RLock()
        self._data: dict[str, Any] = {}

    def load(self) -> dict[str, Any]:
        with self._lock:
            if not self.path.exists():
                self._data = {}
                return {}
            try:
                value = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise SettingsError(f"could not read settings from {self.path}") from exc
            if not isinstance(value, dict):
                raise SettingsError("settings root must be a JSON object")
            self._data = dict(value)
            return dict(self._data)

    def save(self, data: Mapping[str, Any] | None = None) -> None:
        with self._lock:
            if data is not None:
                self._data = dict(data)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent, delete=False) as handle:
                    json.dump(self._data, handle, ensure_ascii=False, indent=2)
                    handle.write("\n")
                    temporary_path = Path(handle.name)
                temporary_path.replace(self.path)
            except OSError as exc:
                raise SettingsError(f"could not write settings to {self.path}") from exc

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value

    def update(self, values: Mapping[str, Any]) -> None:
        with self._lock:
            self._data.update(values)


class SettingsError(RuntimeError):
    """Raised when settings cannot be safely loaded or saved."""
