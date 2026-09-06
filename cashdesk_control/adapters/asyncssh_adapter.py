"""Optional AsyncSSH adapters.

Importing this module does not require asyncssh. The dependency is loaded only
when a connection is opened, so the core and tests remain usable offline.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..core.models import ConnectionProfile, JumpHost, TunnelDirection, TunnelSpec


class AsyncSSHSessionTransport:
    """Open one SSH control connection, optionally through jump hosts."""

    def __init__(self, credential_resolver: Callable[[str], str | None] | None = None) -> None:
        self.connection: Any = None
        self._jump_connections: list[Any] = []
        self.credential_resolver = credential_resolver

    async def open(self, profile: ConnectionProfile) -> None:
        asyncssh = _load_asyncssh()
        tunnel: Any = None
        try:
            for jump in profile.jump_hosts:
                kwargs = _connect_kwargs(jump, self.credential_resolver)
                kwargs["tunnel"] = tunnel
                jump_connection = await asyncssh.connect(**kwargs)
                self._jump_connections.append(jump_connection)
                tunnel = jump_connection

            kwargs: dict[str, Any] = {
                "host": profile.host,
                "port": profile.port,
                "username": profile.username,
            }
            # Omitting known_hosts keeps AsyncSSH's secure platform default;
            # an explicit profile path can opt into a separate known-hosts file.
            if profile.known_hosts:
                kwargs["known_hosts"] = profile.known_hosts
            if profile.private_key:
                kwargs["client_keys"] = [profile.private_key]
            elif profile.credential_ref and self.credential_resolver:
                password = self.credential_resolver(profile.credential_ref)
                if password is not None:
                    kwargs["password"] = password
            if tunnel is not None:
                kwargs["tunnel"] = tunnel
            self.connection = await asyncssh.connect(**kwargs)
        except Exception:
            await self.close()
            raise

    async def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            await self.connection.wait_closed()
            self.connection = None
        while self._jump_connections:
            connection = self._jump_connections.pop()
            connection.close()
            await connection.wait_closed()


class AsyncSSHTunnelBackend:
    """Use an opened AsyncSSH connection to create local/remote forwards."""

    def __init__(self, transport: AsyncSSHSessionTransport) -> None:
        self.transport = transport

    async def open(self, spec: TunnelSpec) -> Any:
        if self.transport.connection is None:
            raise RuntimeError("SSH session must be connected before starting a tunnel")
        if spec.direction is TunnelDirection.LOCAL:
            return await self.transport.connection.forward_local_port(
                spec.local_host,
                spec.local_port,
                spec.target_host,
                spec.target_port,
            )
        remote_port = spec.remote_port or spec.local_port
        return await self.transport.connection.forward_remote_port(
            spec.remote_host,
            remote_port,
            spec.target_host,
            spec.target_port,
        )

    async def close(self, handle: Any) -> None:
        handle.close()
        wait_closed = getattr(handle, "wait_closed", None)
        if wait_closed is not None:
            result = wait_closed()
            if result is not None:
                await result


def _connect_kwargs(host: JumpHost, credential_resolver: Callable[[str], str | None] | None) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "host": host.host,
        "port": host.port,
        "username": host.username,
        # Do not disable host-key verification for jump hosts. AsyncSSH uses
        # its secure platform known_hosts default when this argument is absent.
    }
    if host.credential_ref and credential_resolver:
        password = credential_resolver(host.credential_ref)
        if password is not None:
            kwargs["password"] = password
    return kwargs


def _load_asyncssh() -> Any:
    try:
        import asyncssh
    except ImportError as exc:
        raise RuntimeError("AsyncSSH support is optional; install 'asyncssh' to connect") from exc
    return asyncssh
