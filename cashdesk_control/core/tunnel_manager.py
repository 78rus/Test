"""Collection and port-conflict checks for SSH tunnels."""

from __future__ import annotations

import asyncio
from threading import RLock

from .events import EventBus
from .models import TunnelDirection, TunnelSpec
from .session import KassSession
from .tunnel import SSHTunnel, TunnelBackend, TunnelSnapshot


class TunnelManager:
    """Own all forwards belonging to the active application sessions."""

    def __init__(self, events: EventBus | None = None) -> None:
        self.events = events or EventBus()
        self._tunnels: dict[str, SSHTunnel] = {}
        self._owners: dict[str, KassSession | None] = {}
        self._lock = RLock()

    def add(self, spec: TunnelSpec, backend: TunnelBackend, session: KassSession | None = None) -> SSHTunnel:
        with self._lock:
            if spec.tunnel_id in self._tunnels:
                raise DuplicateTunnelError(spec.tunnel_id)
            self._assert_port_available(spec)
            tunnel = SSHTunnel(spec, backend, self.events)
            self._tunnels[spec.tunnel_id] = tunnel
            self._owners[spec.tunnel_id] = session
        self.events.emit("tunnel.created", spec.tunnel_id, snapshot=tunnel.snapshot())
        return tunnel

    def get(self, tunnel_id: str) -> SSHTunnel:
        with self._lock:
            try:
                return self._tunnels[tunnel_id]
            except KeyError as exc:
                raise TunnelNotFoundError(tunnel_id) from exc

    def snapshots(self) -> tuple[TunnelSnapshot, ...]:
        with self._lock:
            tunnels = tuple(self._tunnels.values())
        return tuple(tunnel.snapshot() for tunnel in tunnels)

    async def start(self, tunnel_id: str) -> SSHTunnel:
        tunnel = self.get(tunnel_id)
        await tunnel.start()
        owner = self._owners.get(tunnel_id)
        if owner is not None:
            owner.attach_tunnel(tunnel_id)
        self.events.emit("tunnel.started", tunnel_id, snapshot=tunnel.snapshot())
        return tunnel

    async def stop(self, tunnel_id: str) -> None:
        tunnel = self.get(tunnel_id)
        await tunnel.stop()
        owner = self._owners.get(tunnel_id)
        if owner is not None:
            owner.detach_tunnel(tunnel_id)
        self.events.emit("tunnel.stopped", tunnel_id, snapshot=tunnel.snapshot())

    async def start_all(self, tunnel_ids: tuple[str, ...] | None = None) -> tuple[SSHTunnel, ...]:
        ids = tunnel_ids if tunnel_ids is not None else tuple(self._tunnels)
        if not ids:
            return ()
        results = await asyncio.gather(*(self.start(tunnel_id) for tunnel_id in ids), return_exceptions=True)
        errors = [result for result in results if isinstance(result, Exception)]
        if errors:
            raise TunnelBatchError(errors)
        return tuple(result for result in results if isinstance(result, SSHTunnel))

    async def stop_all(self) -> None:
        with self._lock:
            ids = tuple(self._tunnels)
        if ids:
            await asyncio.gather(*(self.stop(tunnel_id) for tunnel_id in ids))

    async def remove(self, tunnel_id: str) -> None:
        tunnel = self.get(tunnel_id)
        await tunnel.stop()
        owner = self._owners.get(tunnel_id)
        if owner is not None:
            owner.detach_tunnel(tunnel_id)
        with self._lock:
            self._tunnels.pop(tunnel_id, None)
            self._owners.pop(tunnel_id, None)
        self.events.emit("tunnel.removed", tunnel_id)

    def _assert_port_available(self, spec: TunnelSpec) -> None:
        for existing in self._tunnels.values():
            if existing.spec.direction is not spec.direction:
                continue
            existing_bind_host = existing.spec.remote_host if existing.spec.direction is TunnelDirection.REMOTE else existing.spec.local_host
            bind_host = spec.remote_host if spec.direction is TunnelDirection.REMOTE else spec.local_host
            if existing_bind_host == bind_host and existing.spec.bind_port == spec.bind_port:
                raise TunnelConflictError(f"{bind_host}:{spec.bind_port} is already reserved by {existing.tunnel_id}")


class TunnelManagerError(RuntimeError):
    """Base class for tunnel collection errors."""


class DuplicateTunnelError(TunnelManagerError):
    """Raised when a tunnel id already exists."""


class TunnelNotFoundError(TunnelManagerError):
    """Raised when a requested tunnel id is not registered."""


class TunnelConflictError(TunnelManagerError):
    """Raised when two forwards try to claim the same bind endpoint."""


class TunnelBatchError(TunnelManagerError):
    """Raised when at least one tunnel in a batch fails to start."""

    def __init__(self, errors: list[Exception]) -> None:
        self.errors = tuple(errors)
        super().__init__(f"{len(errors)} tunnel(s) failed to start")
