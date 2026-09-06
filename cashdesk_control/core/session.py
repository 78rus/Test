"""Logical cashier session and its transport contract."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Protocol

from .events import EventBus
from .models import ConnectionProfile, SessionSnapshot, SessionState


class SessionTransport(Protocol):
    """Minimal async contract implemented by AsyncSSH and test transports."""

    async def open(self, profile: ConnectionProfile) -> None:
        """Open the control channel for *profile*."""

    async def close(self) -> None:
        """Close the control channel."""


class KassSession:
    """Owns one cashier's logical lifecycle.

    The class does not know about Qt or a concrete SSH library. A transport is
    injected by the adapter layer, which keeps the session manager testable and
    lets the GUI remain responsive when a connection is replaced.
    """

    def __init__(self, profile: ConnectionProfile, events: EventBus | None = None) -> None:
        self.profile = profile
        self.events = events or EventBus()
        self._state = SessionState.DISCONNECTED
        self._connected_at: datetime | None = None
        self._last_error: str | None = None
        self._transport: SessionTransport | None = None
        self._tunnel_ids: set[str] = set()
        self._lock = RLock()

    @property
    def session_id(self) -> str:
        return self.profile.profile_id

    @property
    def state(self) -> SessionState:
        with self._lock:
            return self._state

    @property
    def is_active(self) -> bool:
        return self.state in {SessionState.CONNECTING, SessionState.CONNECTED, SessionState.DEGRADED}

    @property
    def tunnel_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._tunnel_ids))

    async def connect(self, transport: SessionTransport) -> None:
        """Open the injected transport and publish lifecycle events."""

        with self._lock:
            if self._state is SessionState.CONNECTED:
                return
            if self._state is SessionState.CONNECTING:
                raise SessionLifecycleError("session is already connecting")
            self._last_error = None
            self._transport = transport
            self._set_state_locked(SessionState.CONNECTING)

        try:
            await transport.open(self.profile)
        except asyncio.CancelledError:
            with self._lock:
                self._transport = None
                self._set_state_locked(SessionState.DISCONNECTED)
            raise
        except Exception as exc:
            with self._lock:
                self._transport = None
                self._last_error = str(exc) or exc.__class__.__name__
                self._set_state_locked(SessionState.ERROR)
            raise SessionConnectionError(self._last_error) from exc

        with self._lock:
            self._connected_at = datetime.now(timezone.utc)
            self._set_state_locked(SessionState.CONNECTED)

    async def disconnect(self) -> None:
        """Close the transport, regardless of its current state."""

        with self._lock:
            transport = self._transport
            if self._state is SessionState.DISCONNECTED and transport is None:
                return
            self._set_state_locked(SessionState.CLOSING)

        try:
            if transport is not None:
                await transport.close()
        finally:
            with self._lock:
                self._transport = None
                self._connected_at = None
                self._set_state_locked(SessionState.DISCONNECTED)

    def mark_degraded(self, reason: str) -> None:
        with self._lock:
            self._last_error = reason
            if self._state in {SessionState.CONNECTED, SessionState.DEGRADED}:
                self._set_state_locked(SessionState.DEGRADED)

    def mark_error(self, reason: str) -> None:
        with self._lock:
            self._last_error = reason
            self._set_state_locked(SessionState.ERROR)

    def attach_tunnel(self, tunnel_id: str) -> None:
        if not tunnel_id.strip():
            raise ValueError("tunnel_id must not be empty")
        with self._lock:
            self._tunnel_ids.add(tunnel_id)
        self.events.emit("session.tunnel_attached", self.session_id, tunnel_id=tunnel_id)

    def detach_tunnel(self, tunnel_id: str) -> None:
        with self._lock:
            self._tunnel_ids.discard(tunnel_id)
        self.events.emit("session.tunnel_detached", self.session_id, tunnel_id=tunnel_id)

    def snapshot(self) -> SessionSnapshot:
        with self._lock:
            return SessionSnapshot(
                session_id=self.session_id,
                name=self.profile.name,
                host=self.profile.host,
                state=self._state,
                connected_at=self._connected_at.isoformat() if self._connected_at else None,
                last_error=self._last_error,
                tunnel_ids=tuple(sorted(self._tunnel_ids)),
            )

    def _set_state_locked(self, state: SessionState) -> None:
        previous = self._state
        self._state = state
        if previous is not state:
            self.events.emit(
                "session.state_changed",
                self.session_id,
                previous=previous.value,
                state=state.value,
                snapshot=self.snapshot(),
            )


class SessionLifecycleError(RuntimeError):
    """Raised when a lifecycle operation conflicts with the current state."""


class SessionConnectionError(RuntimeError):
    """Raised when the injected transport cannot be opened."""
