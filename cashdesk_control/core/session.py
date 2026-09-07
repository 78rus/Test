"""Logical cashier session and its transport contract."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Mapping, Protocol

from .events import EventBus
from .models import CommandResult, ConnectionProfile, SessionSnapshot, SessionState


class SessionTransport(Protocol):
    """Minimal async contract implemented by AsyncSSH and test transports."""

    async def open(self, profile: ConnectionProfile) -> None:
        """Open the control channel for *profile*."""

    async def close(self) -> None:
        """Close the control channel."""


class CommandCapableTransport(SessionTransport, Protocol):
    """A transport that can also execute shell commands."""

    async def run(self, command: str, *, timeout: float = 60.0, sudo_password: str | None = None) -> CommandResult:
        """Execute *command* and return its result."""


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
        self._transport: Any = None
        self._tunnel_ids: set[str] = set()
        self._facts: dict[str, str] = {}
        self._sudo_resolver: Any = None
        self._lock = RLock()

    # -- identity -----------------------------------------------------------
    @property
    def session_id(self) -> str:
        return self.profile.profile_id

    @property
    def name(self) -> str:
        return self.profile.name

    @property
    def host(self) -> str:
        return self.profile.host

    # -- state --------------------------------------------------------------
    @property
    def state(self) -> SessionState:
        with self._lock:
            return self._state

    @property
    def is_active(self) -> bool:
        return self.state in {SessionState.CONNECTING, SessionState.CONNECTED, SessionState.DEGRADED}

    @property
    def is_connected(self) -> bool:
        return self.state is SessionState.CONNECTED and self._transport is not None

    @property
    def transport(self) -> Any:
        with self._lock:
            return self._transport

    @property
    def tunnel_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._tunnel_ids))

    @property
    def last_error(self) -> str | None:
        with self._lock:
            return self._last_error

    @property
    def facts(self) -> Mapping[str, str]:
        with self._lock:
            return dict(self._facts)

    def set_sudo_resolver(self, resolver: Any) -> None:
        """Register the callback that returns the sudo password, if stored."""

        self._sudo_resolver = resolver

    def update_profile(self, profile: ConnectionProfile) -> None:
        """Replace the profile (after an edit) and notify listeners."""

        if profile.profile_id != self.profile.profile_id:
            raise ValueError("profile id cannot change for an existing session")
        self.profile = profile
        self.events.emit("session.profile_changed", self.session_id, snapshot=self.snapshot())

    def set_facts(self, facts: Mapping[str, str]) -> None:
        """Store the facts extracted from the latest summary report."""

        with self._lock:
            self._facts = dict(facts)
        self.events.emit("session.facts_changed", self.session_id, snapshot=self.snapshot())

    # -- lifecycle ----------------------------------------------------------
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

    def mark_healthy(self) -> None:
        with self._lock:
            self._last_error = None
            if self._state is SessionState.DEGRADED and self._transport is not None:
                self._set_state_locked(SessionState.CONNECTED)

    # -- command execution ---------------------------------------------------
    def _sudo_password(self) -> str | None:
        reference = self.profile.sudo_credential_ref or self.profile.credential_ref
        if not reference or self._sudo_resolver is None:
            return None
        try:
            return self._sudo_resolver(reference)
        except Exception:
            return None

    async def run(self, command: str, *, timeout: float = 60.0, sudo_password: str | None = None) -> CommandResult:
        """Run *command* on the cashier.

        Returns a :class:`CommandResult` even when the transport is gone, so the
        UI always has something to render instead of an exception dialog.
        """

        transport = self.transport
        if transport is None:
            return CommandResult(command=command, error="сессия не подключена")
        runner = getattr(transport, "run", None)
        if runner is None:
            return CommandResult(command=command, error="транспорт не поддерживает выполнение команд")
        secret = sudo_password if sudo_password is not None else self._sudo_password()
        result = await runner(command, timeout=timeout, sudo_password=secret)
        if result.error and "не подключена" in (result.error or ""):
            self.mark_degraded(result.error)
        return result

    # -- tunnels -------------------------------------------------------------
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
                kass_type=self.profile.kass_type,
                location=self.profile.location,
                color=self.profile.color,
                version=self._facts.get("cash_version", ""),
                uptime=self._facts.get("uptime", ""),
                facts=dict(self._facts),
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
