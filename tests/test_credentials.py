"""Secret storage: encrypted fallback vault and the keyring chain."""

from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path

from cashdesk_control.adapters.credentials import (
    ChainedCredentialStore,
    CredentialStoreError,
    EncryptedFileStore,
    KeyringCredentialStore,
    default_store,
)


class EncryptedFileStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.vault = Path(self._temp.name) / "secrets.vault"
        self.store = EncryptedFileStore(self.vault)

    def test_round_trip(self) -> None:
        self.store.set("ssh:abc", "hunter2")
        self.assertEqual(self.store.get("ssh:abc"), "hunter2")

    def test_missing_reference_returns_none(self) -> None:
        self.assertIsNone(self.store.get("nope"))

    def test_delete(self) -> None:
        self.store.set("ssh:abc", "hunter2")
        self.store.delete("ssh:abc")
        self.assertIsNone(self.store.get("ssh:abc"))

    def test_vault_is_not_plaintext(self) -> None:
        self.store.set("ssh:abc", "hunter2")
        raw = self.vault.read_bytes()
        self.assertNotIn(b"hunter2", raw)

    def test_key_file_is_owner_only(self) -> None:
        self.store.set("ssh:abc", "hunter2")
        mode = stat.S_IMODE(self.store.key_path.stat().st_mode)
        self.assertEqual(mode, 0o600)

    def test_a_fresh_store_cannot_read_another_key(self) -> None:
        self.store.set("ssh:abc", "hunter2")
        other = EncryptedFileStore(self.vault)
        other.key_path.write_bytes(b"")  # simulate a lost key file
        other.key_path.unlink()
        # A regenerated key must not decrypt the old payload.
        self.assertIsNone(other.get("ssh:abc"))

    def test_unicode_values_survive(self) -> None:
        self.store.set("vnc:1", "пароль-Ω")
        self.assertEqual(self.store.get("vnc:1"), "пароль-Ω")


class BrokenKeyring:
    backend = "broken"

    def __init__(self) -> None:
        self.calls = 0

    def set(self, reference: str, secret: str) -> None:
        self.calls += 1
        raise CredentialStoreError("no keyring backend")

    def get(self, reference: str) -> str | None:
        self.calls += 1
        raise CredentialStoreError("no keyring backend")

    def delete(self, reference: str) -> None:
        self.calls += 1


class WorkingKeyring:
    backend = "keyring"

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def set(self, reference: str, secret: str) -> None:
        self.values[reference] = secret

    def get(self, reference: str) -> str | None:
        return self.values.get(reference)

    def delete(self, reference: str) -> None:
        self.values.pop(reference, None)


class ChainedStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.vault = Path(self._temp.name) / "secrets.vault"

    def test_primary_is_used_when_it_works(self) -> None:
        primary = WorkingKeyring()
        chain = ChainedCredentialStore(primary, EncryptedFileStore(self.vault))
        chain.set("ssh:1", "secret")
        self.assertEqual(chain.backend, "keyring")
        self.assertEqual(chain.get("ssh:1"), "secret")
        self.assertFalse(self.vault.exists())

    def test_falls_back_when_the_keyring_breaks(self) -> None:
        primary = BrokenKeyring()
        chain = ChainedCredentialStore(primary, EncryptedFileStore(self.vault))
        chain.set("ssh:1", "secret")
        self.assertEqual(chain.backend, "file (шифрованный)")
        self.assertEqual(chain.get("ssh:1"), "secret")
        self.assertTrue(self.vault.exists())

    def test_read_falls_back_for_secrets_written_to_the_file(self) -> None:
        EncryptedFileStore(self.vault).set("ssh:old", "old-secret")
        chain = ChainedCredentialStore(WorkingKeyring(), EncryptedFileStore(self.vault))
        self.assertEqual(chain.get("ssh:old"), "old-secret")

    def test_delete_touches_both_stores(self) -> None:
        primary = WorkingKeyring()
        fallback = EncryptedFileStore(self.vault)
        fallback.set("ssh:1", "x")
        primary.set("ssh:1", "x")
        chain = ChainedCredentialStore(primary, fallback)
        chain.delete("ssh:1")
        self.assertEqual(primary.values, {})
        self.assertIsNone(fallback.get("ssh:1"))


class DefaultStoreTests(unittest.TestCase):
    def test_returns_a_chain(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = default_store(Path(directory) / "secrets.vault")
            self.assertIsInstance(store, ChainedCredentialStore)
            self.assertIsInstance(store.primary, KeyringCredentialStore)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
