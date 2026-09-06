"""Optional OS keyring credential adapter."""

from __future__ import annotations


class KeyringCredentialStore:
    """Store secret values in the operating system keyring, never in JSON."""

    def __init__(self, service_name: str = "cashdesk-control") -> None:
        self.service_name = service_name

    def set(self, reference: str, secret: str) -> None:
        keyring = self._keyring()
        keyring.set_password(self.service_name, reference, secret)

    def get(self, reference: str) -> str | None:
        keyring = self._keyring()
        return keyring.get_password(self.service_name, reference)

    def delete(self, reference: str) -> None:
        keyring = self._keyring()
        try:
            keyring.delete_password(self.service_name, reference)
        except keyring.errors.PasswordDeleteError:
            return

    @staticmethod
    def _keyring():
        try:
            import keyring
        except ImportError as exc:
            raise RuntimeError("secure credential storage requires the optional 'keyring' package") from exc
        return keyring
