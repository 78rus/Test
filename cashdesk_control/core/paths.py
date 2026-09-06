"""Portable application directories for Windows, macOS and Linux."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppPaths:
    """Directories used by the desktop application."""

    config_dir: Path
    data_dir: Path
    log_dir: Path
    cache_dir: Path

    @property
    def settings_file(self) -> Path:
        return self.config_dir / "settings.json"

    @property
    def profiles_file(self) -> Path:
        return self.config_dir / "profiles.json"

    @property
    def log_file(self) -> Path:
        return self.log_dir / "cashdesk-control.log"

    def ensure(self) -> "AppPaths":
        for directory in (self.config_dir, self.data_dir, self.log_dir, self.cache_dir):
            directory.mkdir(parents=True, exist_ok=True)
        return self


def app_paths(app_name: str = "Cashdesk Control") -> AppPaths:
    """Return OS-appropriate writable paths without requiring platformdirs.

    On Windows configuration and logs live under ``%APPDATA%`` and cache data
    under ``%LOCALAPPDATA%``. The function is intentionally dependency-free so
    it works both from source and inside a PyInstaller build.
    """

    safe_name = app_name.strip() or "Cashdesk Control"
    if sys.platform == "win32":
        roaming = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return AppPaths(
            config_dir=roaming / safe_name,
            data_dir=roaming / safe_name / "data",
            log_dir=roaming / safe_name / "logs",
            cache_dir=local / safe_name / "cache",
        )
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / safe_name
        return AppPaths(base, base / "data", base / "logs", base / "cache")

    config_base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    data_base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    cache_base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return AppPaths(
        config_dir=config_base / safe_name.lower().replace(" ", "-"),
        data_dir=data_base / safe_name.lower().replace(" ", "-"),
        log_dir=data_base / safe_name.lower().replace(" ", "-") / "logs",
        cache_dir=cache_base / safe_name.lower().replace(" ", "-"),
    )
