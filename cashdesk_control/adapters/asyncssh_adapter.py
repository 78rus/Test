"""Real SSH transport built on AsyncSSH.

Importing this module does not require ``asyncssh``; the dependency is loaded
when a connection is actually opened so the core and the test-suite stay usable
on a machine without it.
"""

from __future__ import annotations

import asyncio
import logging
import shlex
import time
from collections.abc import Callable
from typing import Any

from ..core.models import CommandResult, ConnectionProfile, JumpHost, TunnelDirection, TunnelSpec

logger = logging.getLogger("cashdesk_control.ssh")

CredentialResolver = Callable[[str], str | None]


class AsyncSSHSessionTransport:
    """One SSH control connection, optionally through jump hosts.

    The transport exposes exactly the operations the UI needs — run a command,
    open an interactive PTY, list and copy files, forward ports — without
    leaking AsyncSSH types into the core.
    """

    def __init__(self, credential_resolver: CredentialResolver | None = None) -> None:
        self.connection: Any = None
        self.profile: ConnectionProfile | None = None
        self._jump_connections: list[Any] = []
        self.credential_resolver = credential_resolver

    @property
    def is_open(self) -> bool:
        return self.connection is not None

    @property
    def banner(self) -> str:
        if self.connection is None or self.profile is None:
            return "нет соединения"
        return f"{self.profile.username}@{self.profile.host}:{self.profile.port}"

    # -- lifecycle ---------------------------------------------------------
    async def open(self, profile: ConnectionProfile) -> None:
        asyncssh = _load_asyncssh()
        self.profile = profile
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
                "keepalive_interval": 15,
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
            try:
                self.connection.close()
                await self.connection.wait_closed()
            except Exception as exc:  # pragma: no cover - best effort teardown
                logger.debug("ssh close warning: %s", exc)
            self.connection = None
        while self._jump_connections:
            connection = self._jump_connections.pop()
            try:
                connection.close()
                await connection.wait_closed()
            except Exception as exc:  # pragma: no cover - best effort teardown
                logger.debug("ssh jump close warning: %s", exc)
        self.profile = None

    # -- command execution --------------------------------------------------
    def _shell_prefix(self) -> str:
        """Export the cashier ``PATH`` so ``cash`` resolves in a non-login shell."""

        profile = self.profile
        if profile is None or not profile.remote_path:
            return ""
        return f"export PATH={shlex.quote(profile.remote_path)}:$PATH; "

    async def run(
        self,
        command: str,
        *,
        timeout: float = 60.0,
        sudo_password: str | None = None,
    ) -> CommandResult:
        """Run one command and return stdout, stderr, exit code and timing.

        A timeout or a broken channel is reported through ``CommandResult.error``
        rather than raised, so a report can keep collecting the other probes.
        """

        if self.connection is None:
            return CommandResult(command=command, error="SSH-сессия не подключена")
        full_command = self._shell_prefix() + command
        stdin_data: str | None = None
        if sudo_password and command.strip().startswith("sudo "):
            full_command = self._shell_prefix() + command.replace("sudo ", "sudo -S -p '' ", 1)
            stdin_data = sudo_password + "\n"
        started = time.monotonic()
        try:
            process = await asyncio.wait_for(
                self.connection.run(full_command, check=False, input=stdin_data),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            elapsed = (time.monotonic() - started) * 1000
            return CommandResult(command=command, error=f"таймаут {timeout:.0f} с", duration_ms=elapsed)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            elapsed = (time.monotonic() - started) * 1000
            return CommandResult(command=command, error=str(exc) or exc.__class__.__name__, duration_ms=elapsed)
        elapsed = (time.monotonic() - started) * 1000
        return CommandResult(
            command=command,
            stdout=str(process.stdout or ""),
            stderr=str(process.stderr or ""),
            exit_code=int(process.exit_status or 0),
            duration_ms=elapsed,
        )

    #: Alias kept for callers written against the earlier contract.
    async def run_command(self, command: str, *, check: bool = False, **kwargs: Any) -> str:
        result = await self.run(command, **kwargs)
        if result.error:
            raise RuntimeError(result.error)
        if check and result.exit_code != 0:
            raise RuntimeError(result.stderr.strip() or f"exit status {result.exit_code}")
        return result.stdout

    # -- interactive shell ---------------------------------------------------
    async def open_terminal(self, *, term_type: str = "xterm-256color", term_size: tuple[int, int] = (120, 32)) -> Any:
        if self.connection is None:
            raise RuntimeError("SSH-сессия не подключена")
        process = await self.connection.create_process(
            term_type=term_type,
            term_size=term_size,
            encoding=None,
        )
        return process

    async def resize_terminal(self, process: Any, columns: int, rows: int) -> None:
        try:
            process.change_terminal_size(columns, rows)
        except Exception as exc:  # pragma: no cover - server dependent
            logger.debug("terminal resize failed: %s", exc)

    # -- SFTP ----------------------------------------------------------------
    async def open_sftp(self) -> Any:
        if self.connection is None:
            raise RuntimeError("SSH-сессия не подключена")
        return await self.connection.start_sftp_client()

    # -- port forwarding -----------------------------------------------------
    async def forward_local(self, spec: TunnelSpec) -> Any:
        if self.connection is None:
            raise RuntimeError("SSH-сессия не подключена")
        return await self.connection.forward_local_port(
            spec.local_host,
            spec.local_port,
            spec.target_host,
            spec.target_port,
        )

    async def forward_remote(self, spec: TunnelSpec) -> Any:
        if self.connection is None:
            raise RuntimeError("SSH-сессия не подключена")
        return await self.connection.forward_remote_port(
            spec.remote_host,
            spec.remote_port or spec.local_port,
            spec.target_host,
            spec.target_port,
        )


class AsyncSSHTunnelBackend:
    """Use an opened AsyncSSH connection to create local/remote forwards."""

    def __init__(self, transport: AsyncSSHSessionTransport) -> None:
        self.transport = transport

    async def open(self, spec: TunnelSpec) -> Any:
        if self.transport.connection is None:
            raise RuntimeError("SSH session must be connected before starting a tunnel")
        if spec.direction is TunnelDirection.LOCAL:
            return await self.transport.forward_local(spec)
        return await self.transport.forward_remote(spec)

    async def close(self, handle: Any) -> None:
        handle.close()
        wait_closed = getattr(handle, "wait_closed", None)
        if wait_closed is not None:
            result = wait_closed()
            if result is not None:
                await result


class LocalProcessTransport:
    """Run commands on the machine the application runs on.

    Useful when the engineer sits at the cashier itself, and it is what makes the
    report and quick commands testable without hardware.
    """

    def __init__(self, shell: str = "/bin/bash") -> None:
        self.shell = shell
        self._open = False
        self.profile: ConnectionProfile | None = None

    @property
    def is_open(self) -> bool:
        return self._open

    @property
    def banner(self) -> str:
        return "локальная машина"

    async def open(self, profile: ConnectionProfile) -> None:
        process = await asyncio.create_subprocess_exec(self.shell, "-c", "exit 0")
        await process.wait()
        self.profile = profile
        self._open = True

    async def close(self) -> None:
        self._open = False
        self.profile = None

    async def run(
        self,
        command: str,
        *,
        timeout: float = 60.0,
        sudo_password: str | None = None,
    ) -> CommandResult:
        if not self._open:
            return CommandResult(command=command, error="локальный транспорт не открыт")
        executable = command
        stdin_data: bytes | None = None
        if sudo_password and command.strip().startswith("sudo "):
            executable = command.replace("sudo ", "sudo -S -p '' ", 1)
            stdin_data = (sudo_password + "\n").encode()
        started = time.monotonic()
        try:
            process = await asyncio.create_subprocess_exec(
                self.shell,
                "-c",
                executable,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE if stdin_data is not None else None,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(stdin_data), timeout=timeout)
        except asyncio.TimeoutError:
            process.kill()
            elapsed = (time.monotonic() - started) * 1000
            return CommandResult(command=command, error=f"таймаут {timeout:.0f} с", duration_ms=elapsed)
        except Exception as exc:
            elapsed = (time.monotonic() - started) * 1000
            return CommandResult(command=command, error=str(exc) or exc.__class__.__name__, duration_ms=elapsed)
        elapsed = (time.monotonic() - started) * 1000
        return CommandResult(
            command=command,
            stdout=stdout.decode("utf-8", "replace"),
            stderr=stderr.decode("utf-8", "replace"),
            exit_code=int(process.returncode or 0),
            duration_ms=elapsed,
        )


def _connect_kwargs(host: JumpHost, credential_resolver: CredentialResolver | None) -> dict[str, Any]:
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
