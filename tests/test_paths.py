from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cashdesk_control.core.paths import app_paths


class AppPathsTests(unittest.TestCase):
    def test_windows_paths_use_appdata_and_localappdata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(sys, "platform", "win32"), patch.dict(
                os.environ,
                {"APPDATA": str(root / "roaming"), "LOCALAPPDATA": str(root / "local")},
                clear=False,
            ):
                paths = app_paths()
            self.assertEqual(paths.config_dir, root / "roaming" / "Cashdesk Control")
            self.assertEqual(paths.cache_dir, root / "local" / "Cashdesk Control" / "cache")
            self.assertTrue(str(paths.settings_file).endswith("settings.json"))

    def test_ensure_creates_all_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "app"
            with patch.object(sys, "platform", "win32"), patch.dict(
                os.environ,
                {"APPDATA": str(root / "roaming"), "LOCALAPPDATA": str(root / "local")},
                clear=False,
            ):
                paths = app_paths().ensure()
            self.assertTrue(paths.config_dir.is_dir())
            self.assertTrue(paths.data_dir.is_dir())
            self.assertTrue(paths.log_dir.is_dir())
            self.assertTrue(paths.cache_dir.is_dir())


if __name__ == "__main__":
    unittest.main()
