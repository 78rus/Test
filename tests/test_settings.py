from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cashdesk_control.core.models import ConnectionProfile
from cashdesk_control.core.profiles import ProfileStore
from cashdesk_control.core.settings import SettingsStore


class SettingsStoreTests(unittest.TestCase):
    def test_settings_are_saved_and_loaded_as_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            store = SettingsStore(path)
            store.set("theme", "dark")
            store.set("max_sessions", 10)
            store.save()

            loaded = SettingsStore(path)
            self.assertEqual(loaded.load(), {"theme": "dark", "max_sessions": 10})
            self.assertEqual(loaded.get("theme"), "dark")

    def test_profile_store_persists_profile_without_a_password(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = SettingsStore(Path(directory) / "settings.json")
            profiles = ProfileStore(settings)
            profiles.upsert(ConnectionProfile("Склад", "10.24.8.41", "operator", profile_id="warehouse", credential_ref="warehouse-ssh"))
            profiles.save()

            restored_settings = SettingsStore(Path(directory) / "settings.json")
            restored_settings.load()
            restored = ProfileStore(restored_settings)
            loaded = restored.load()
            self.assertEqual(loaded[0].profile_id, "warehouse")
            self.assertEqual(loaded[0].credential_ref, "warehouse-ssh")
            self.assertNotIn("password", restored_settings.get("connection_profiles")[0])


if __name__ == "__main__":
    unittest.main()
