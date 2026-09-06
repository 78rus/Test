"""Lifecycle state machine for one SSH port forward."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from .events import EventBus
from .models import TunnelSpec


class TunnelState(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    ACTIVE = "active"
    RECONNECTING = "reconnecting"
    ERROR = "error"
    STOPPING = "stopping"


class TunnelBackend(Protocol):
    async def open(self, spec: TunnelSpec) -> Any:
        """Open a port forward and return a backend-specific handle."""

    async def close(self, handle: Any) -> None:
        """Close a backend-specific forward handle."""


@dataclass(frozen=True, slots=True)
class TunnelSnapshot:
    tunnel_id: str
    name: str
    state: TunnelState
    local_port: int
    target: str
    last_error: str | None


class SSHTunnel:
    """A restartable tunnel independent of asyncssh or Qt."""

    def __init__(self, spec: TunnelSpec, backend: TunnelBackend, events: EventBus | None = None) -> None:
        self.spec = spec
        self.backend = backend
        self.events = events or EventBus()
        self._state = TunnelState.STOPPED
        self._handle: Any = None
        self._last_error: str | None = None
        self._stop_requested = False
        self._reconnect_task: asyncio.Task[None] | None = None
        self._operation_lock = asyncio.Lock()

    @property
    def tunnel_id(self) -> str:
        return self.spec.tunnel_id

    @property
    def state(self) -> TunnelState:
        return self._state

    @property
    def is_active(self) -> bool:
        return self._state is TunnelState.ACTIVE

    @property
    def last_error(self) -> str | None:
        return self._last_error

    async def start(self) -> None:
        async with self._operation_lock:
            self._stop_requested = False
            if self._state is TunnelState.ACTIVE:
                return
            await self._open_once()

    async def stop(self) -> None:
        async with self._operation_lock:
            self._stop_requested = True
            reconnect_task = self._reconnect_task
            self._reconnect_task = None
            if reconnect_task and reconnect_task is not asyncio.current_task():
                reconnect_task.cancel()
            self._set_state(TunnelState.STOPPING)
            handle = self._handle
            self._handle = None
            if handle is not None:
                try:
                    await self.backend.close(handle)
                except Exception as exc:
                    self._last_error = str(exc) or exc.__class__.__name__
            self._set_state(TunnelState.STOPPED)

    async def mark_lost(self, reason: str | None = None) -> None:
        """Notify the tunnel that its underlying channel has disappeared."""

        async with self._operation_lock:
            handle = self._handle
            self._handle = None
            if handle is not None:
                try:
                    await self.backend.close(handle)
                except Exception:
                    pass
            self._last_error = reason
            if self._stop_requested or not self.spec.auto_restart:
                self._set_state(TunnelState.ERROR if reason else TunnelState.STOPPED)
                return
            self._set_state(TunnelState.RECONNECTING)
            if self._reconnect_task is None or self._reconnect_task.done():
                self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    def snapshot(self) -> TunnelSnapshot:
        return TunnelSnapshot(
            tunnel_id=self.tunnel_id,
            name=self.spec.name,
            state=self._state,
            local_port=self.spec.bind_port,
            target=f"{self.spec.target_host}:{self.spec.target_port}",
            last_error=self._last_error,
        )

    async def _open_once(self) -> None:
        self._set_state(TunnelState.STARTING)
        try:
            self._handle = await self.backend.open(self.spec)
        except asyncio.CancelledError:
            self._set_state(TunnelState.STOPPED)
            raise
        except Exception as exc:
            self._last_error = str(exc) or exc.__class__.__name__
            self._set_state(TunnelState.ERROR)
            raise TunnelStartError(self._last_error) from exc
        self._last_error = None
        self._set_state(TunnelState.ACTIVE)

    async def _reconnect_loop(self) -> None:
        try:
            while not self._stop_requested:
                await asyncio.sleep(self.spec.reconnect_delay)
                if self._stop_requested:
                    return
                try:
                    async with self._operation_lock:
                        if self._stop_requested:
                            return
                        await self._open_once()
                    return
                except asyncio.CancelledError:
                    raise
                except TunnelStartError:
                    self._set_state(TunnelState.RECONNECTING)
        finally:
            if asyncio.current_task() is self._reconnect_task:
                self._reconnect_task = None

    def _set_state(self, state: TunnelState) -> None:
        previous = self._state
        self._state = state
        if previous is not state:
            self.events.emit(
                "tunnel.state_changed",
                self.tunnel_id,
                previous=previous.value,
                state=state.value,
                snapshot=self.snapshot(),
            )


class TunnelStartError(RuntimeError):
    """Raised when a backend cannot start a forward."""
