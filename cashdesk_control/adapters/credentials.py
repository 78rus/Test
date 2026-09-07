"""Where SSH/VNC/database secrets live.

The OS keyring is always preferred: on Windows that is Credential Manager, on
Linux Secret Service, on macOS the Keychain. When no backend is reachable —
a headless Linux box, a container, a locked desktop — the application falls back
to a Fernet-encrypted file next to the configuration, and says so in the status
bar instead of silently storing anything in plain text.
"""

from __future__ import annotations

import json
import logging
import os
import stat
from base64 import urlsafe_b64encode
from pathlib import Path
from threading import RLock
from typing import Any, Protocol

logger = logging.getLogger("cashdesk_control.credentials")

SERVICE_NAME = "cashdesk-control"


class CredentialStore(Protocol):
    """Store and retrieve opaque secret strings by reference."""

    backend: str

    def set(self, reference: str, secret: str) -> None: ...

    def get(self, reference: str) -> str | None: ...

    def delete(self, reference: str) -> None: ...


class KeyringCredentialStore:
    """Secrets in the operating system keyring."""

    backend = "keyring"

    def __init__(self, service_name: str = SERVICE_NAME) -> None:
        self.service_name = service_name
        self._keyring: Any = None
        self._broken: str | None = None

    def _load(self) -> Any:
        if self._keyring is not None:
            return self._keyring
        if self._broken:
            raise CredentialStoreError(self._broken)
        try:
            import keyring
        except ImportError as exc:
            self._broken = "пакет 'keyring' не установлен"
            raise CredentialStoreError(self._broken) from exc
        self._keyring = keyring
        return keyring

    def set(self, reference: str, secret: str) -> None:
        self._load().set_password(self.service_name, reference, secret)

    def get(self, reference: str) -> str | None:
        return self._load().get_password(self.service_name, reference)

    def delete(self, reference: str) -> None:
        keyring = self._load()
        try:
            keyring.delete_password(self.service_name, reference)
        except keyring.errors.PasswordDeleteError:
            return


class EncryptedFileStore:
    """Fallback store: Fernet-encrypted JSON with a 0600 key file beside it."""

    backend = "file"

    def __init__(self, vault_path: str | Path) -> None:
        self.vault_path = Path(vault_path).expanduser()
        self.key_path = self.vault_path.with_suffix(".key")
        self._lock = RLock()

    # -- key material ----------------------------------------------------------
    def _load_key(self) -> bytes:
        if self.key_path.exists():
            key = self.key_path.read_bytes().strip()
            if key:
                return key
        key = _generate_key()
        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        self.key_path.write_bytes(key)
        try:
            os.chmod(self.key_path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:  # pragma: no cover - Windows has no POSIX mode bits
            pass
        return key

    def _fernet(self) -> Any:
        try:
            from cryptography.fernet import Fernet
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise CredentialStoreError("для шифрования нужен пакет 'cryptography'") from exc
        return Fernet(self._load_key())

    # -- storage -----------------------------------------------------------------
    def _read(self) -> dict[str, str]:
        if not self.vault_path.exists():
            return {}
        try:
            payload = self._fernet().decrypt(self.vault_path.read_bytes())
        except Exception as exc:
            logger.warning("credential vault could not be decrypted: %s", exc)
            return {}
        data = json.loads(payload.decode("utf-8"))
        return data if isinstance(data, dict) else {}

    def _write(self, data: dict[str, str]) -> None:
        self.vault_path.parent.mkdir(parents=True, exist_ok=True)
        payload = self._fernet().encrypt(json.dumps(data, ensure_ascii=False).encode("utf-8"))
        self.vault_path.write_bytes(payload)
        try:
            os.chmod(self.vault_path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:  # pragma: no cover - Windows has no POSIX mode bits
            pass

    def set(self, reference: str, secret: str) -> None:
        with self._lock:
            data = self._read()
            data[reference] = secret
            self._write(data)

    def get(self, reference: str) -> str | None:
        with self._lock:
            return self._read().get(reference)

    def delete(self, reference: str) -> None:
        with self._lock:
            data = self._read()
            if data.pop(reference, None) is not None:
                self._write(data)


class ChainedCredentialStore:
    """Try the OS keyring first, fall back to the encrypted file."""

    def __init__(self, primary: CredentialStore, fallback: CredentialStore) -> None:
        self.primary = primary
        self.fallback = fallback
        self._failed_primary = False

    @property
    def backend(self) -> str:
        return "file (шифрованный)" if self._failed_primary else self.primary.backend

    def set(self, reference: str, secret: str) -> None:
        if not self._failed_primary:
            try:
                self.primary.set(reference, secret)
                return
            except Exception as exc:
                self._failed_primary = True
                logger.warning("keyring unavailable (%s); using the encrypted file store", exc)
        self.fallback.set(reference, secret)

    def get(self, reference: str) -> str | None:
        if not self._failed_primary:
            try:
                value = self.primary.get(reference)
                if value is not None:
                    return value
            except Exception as exc:
                self._failed_primary = True
                logger.warning("keyring unavailable (%s); using the encrypted file store", exc)
        return self.fallback.get(reference)

    def delete(self, reference: str) -> None:
        for store in (self.primary, self.fallback):
            try:
                store.delete(reference)
            except Exception as exc:  # pragma: no cover - best effort
                logger.debug("credential delete warning: %s", exc)


def default_store(vault_path: str | Path) -> ChainedCredentialStore:
    """Keyring when it works, encrypted file otherwise."""

    return ChainedCredentialStore(KeyringCredentialStore(), EncryptedFileStore(vault_path))


def _generate_key() -> bytes:
    try:
        from cryptography.fernet import Fernet

        return Fernet.generate_key()
    except ImportError:  # pragma: no cover - optional dependency
        return urlsafe_b64encode(os.urandom(32))


class CredentialStoreError(RuntimeError):
    """Raised when no credential backend can serve the request."""
