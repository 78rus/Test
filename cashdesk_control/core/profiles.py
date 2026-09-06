"""Persistence for connection profiles without secret material."""

from __future__ import annotations

from threading import RLock

from .models import ConnectionProfile


class ProfileStore:
    """Read and write profiles through a :class:`SettingsStore`-like object."""

    def __init__(self, settings) -> None:
        self.settings = settings
        self._lock = RLock()
        self._profiles: dict[str, ConnectionProfile] = {}

    def load(self) -> tuple[ConnectionProfile, ...]:
        with self._lock:
            raw_profiles = self.settings.get("connection_profiles", [])
            if not isinstance(raw_profiles, list):
                raise ProfileStoreError("connection_profiles must be a list")
            self._profiles = {}
            for raw_profile in raw_profiles:
                profile = ConnectionProfile.from_dict(raw_profile)
                if profile.profile_id in self._profiles:
                    raise ProfileStoreError(f"duplicate profile id: {profile.profile_id}")
                self._profiles[profile.profile_id] = profile
            return tuple(self._profiles.values())

    def save(self) -> None:
        with self._lock:
            self.settings.set("connection_profiles", [profile.to_dict() for profile in self._profiles.values()])
            self.settings.save()

    def upsert(self, profile: ConnectionProfile) -> None:
        with self._lock:
            self._profiles[profile.profile_id] = profile

    def get(self, profile_id: str) -> ConnectionProfile:
        with self._lock:
            try:
                return self._profiles[profile_id]
            except KeyError as exc:
                raise ProfileNotFoundError(profile_id) from exc

    def remove(self, profile_id: str) -> None:
        with self._lock:
            if profile_id not in self._profiles:
                raise ProfileNotFoundError(profile_id)
            del self._profiles[profile_id]

    def all(self) -> tuple[ConnectionProfile, ...]:
        with self._lock:
            return tuple(self._profiles.values())


class ProfileStoreError(RuntimeError):
    """Raised for invalid persisted profile data."""


class ProfileNotFoundError(ProfileStoreError):
    """Raised when a profile id is not present."""
