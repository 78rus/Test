"""Management of up to ten concurrent cashier sessions."""

from __future__ import annotations

import asyncio
from threading import RLock
from typing import Iterable

from .events import EventBus
from .models import ConnectionProfile, SessionSnapshot
from .session import KassSession, SessionTransport


class SessionManager:
    """Create, select and close a bounded set of logical sessions."""

    def __init__(self, max_sessions: int = 10, events: EventBus | None = None) -> None:
        if max_sessions < 1:
            raise ValueError("max_sessions must be at least 1")
        self.max_sessions = max_sessions
        self.events = events or EventBus()
        self._sessions: dict[str, KassSession] = {}
        self._active_id: str | None = None
        self._lock = RLock()

    @property
    def active_id(self) -> str | None:
        with self._lock:
            return self._active_id

    @property
    def active_session(self) -> KassSession | None:
        with self._lock:
            return self._sessions.get(self._active_id) if self._active_id else None

    def __len__(self) -> int:
        with self._lock:
            return len(self._sessions)

    def create(self, profile: ConnectionProfile) -> KassSession:
        with self._lock:
            if len(self._sessions) >= self.max_sessions:
                raise SessionLimitError(f"maximum of {self.max_sessions} sessions reached")
            if profile.profile_id in self._sessions:
                raise DuplicateSessionError(profile.profile_id)
            session = KassSession(profile, self.events)
            self._sessions[profile.profile_id] = session
            should_activate = self._active_id is None
            if should_activate:
                self._active_id = profile.profile_id

        self.events.emit("session.created", profile.profile_id, snapshot=session.snapshot())
        if should_activate:
            self.events.emit("session.activated", profile.profile_id, snapshot=session.snapshot())
        return session

    def get(self, session_id: str) -> KassSession:
        with self._lock:
            try:
                return self._sessions[session_id]
            except KeyError as exc:
                raise SessionNotFoundError(session_id) from exc

    def activate(self, session_id: str) -> KassSession:
        session = self.get(session_id)
        with self._lock:
            self._active_id = session_id
        self.events.emit("session.activated", session_id, snapshot=session.snapshot())
        return session

    def snapshots(self) -> tuple[SessionSnapshot, ...]:
        with self._lock:
            sessions = tuple(self._sessions.values())
        return tuple(session.snapshot() for session in sessions)

    def profiles(self) -> tuple[ConnectionProfile, ...]:
        with self._lock:
            return tuple(session.profile for session in self._sessions.values())

    async def connect(self, session_id: str, transport: SessionTransport) -> KassSession:
        session = self.get(session_id)
        await session.connect(transport)
        self.activate(session_id)
        return session

    async def disconnect(self, session_id: str) -> None:
        await self.get(session_id).disconnect()

    async def remove(self, session_id: str) -> None:
        session = self.get(session_id)
        await session.disconnect()
        with self._lock:
            self._sessions.pop(session_id, None)
            was_active = self._active_id == session_id
            if was_active:
                self._active_id = next(iter(self._sessions), None)
            next_active = self._active_id
        self.events.emit("session.removed", session_id)
        if was_active and next_active:
            self.events.emit("session.activated", next_active, snapshot=self.get(next_active).snapshot())

    async def close_all(self) -> None:
        with self._lock:
            sessions = tuple(self._sessions.values())
        if sessions:
            await asyncio.gather(*(session.disconnect() for session in sessions))
        with self._lock:
            removed_ids = tuple(self._sessions)
            self._sessions.clear()
            self._active_id = None
        for session_id in removed_ids:
            self.events.emit("session.removed", session_id)

    def __iter__(self) -> Iterable[KassSession]:
        with self._lock:
            return iter(tuple(self._sessions.values()))


class SessionManagerError(RuntimeError):
    """Base class for session collection errors."""


class SessionLimitError(SessionManagerError):
    """Raised when the configured session limit has been reached."""


class DuplicateSessionError(SessionManagerError):
    """Raised when a profile id is already registered."""


class SessionNotFoundError(SessionManagerError):
    """Raised when a requested session id is not registered."""
