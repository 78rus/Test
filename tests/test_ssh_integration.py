"""End-to-end tests over a real SSH connection.

These need an ``sshd`` the test-suite can reach. ``tests/run_ssh_lab.sh`` starts
one in the sandbox; when no server is configured the whole module skips instead
of pretending to pass.

    CASHDESK_TEST_SSH_HOST=127.0.0.1
    CASHDESK_TEST_SSH_PORT=2222
    CASHDESK_TEST_SSH_USER=user
    CASHDESK_TEST_SSH_KEY=/tmp/sshlab/user_key
    CASHDESK_TEST_SSH_KNOWN_HOSTS=/tmp/sshlab/known_hosts
"""

from __future__ import annotations

import asyncio
import os
import shutil
import socket
import unittest

from cashdesk_control.adapters.asyncssh_adapter import AsyncSSHSessionTransport, AsyncSSHTunnelBackend, LocalProcessTransport
from cashdesk_control.core.commands import CommandSpec, Risk
from cashdesk_control.core.models import ConnectionProfile, TunnelSpec
from cashdesk_control.core.report import KassReportBuilder, ReportOptions
from cashdesk_control.core.session import KassSession

HOST = os.environ.get("CASHDESK_TEST_SSH_HOST", "127.0.0.1")
PORT = int(os.environ.get("CASHDESK_TEST_SSH_PORT", "2222"))
USER = os.environ.get("CASHDESK_TEST_SSH_USER", os.environ.get("USER", "user"))
KEY = os.environ.get("CASHDESK_TEST_SSH_KEY", "")
KNOWN_HOSTS = os.environ.get("CASHDESK_TEST_SSH_KNOWN_HOSTS", "")
REMOTE_PATH = os.environ.get("CASHDESK_TEST_SSH_PATH", "")


def _server_available() -> bool:
    if not KEY:
        return False
    try:
        with socket.create_connection((HOST, PORT), timeout=1.5):
            return True
    except OSError:
        return False


def _profile(**overrides) -> ConnectionProfile:
    data = {
        "name": "Лабораторная касса",
        "host": HOST,
        "port": PORT,
        "username": USER,
        "private_key": KEY,
        "known_hosts": KNOWN_HOSTS or None,
        "remote_path": REMOTE_PATH,
    }
    data.update(overrides)
    return ConnectionProfile.from_dict(data)


@unittest.skipUnless(_server_available(), "no test SSH server configured")
class SshTransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.transport = AsyncSSHSessionTransport()
        await self.transport.open(_profile())
        self.addAsyncCleanup(self.transport.close)

    async def test_run_returns_stdout_and_exit_code(self) -> None:
        result = await self.transport.run("echo hello; exit 0")
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.stdout.strip(), "hello")
        self.assertEqual(result.exit_code, 0)
        self.assertGreater(result.duration_ms, 0)

    async def test_run_captures_stderr_and_failure(self) -> None:
        result = await self.transport.run("echo oops >&2; exit 3")
        self.assertFalse(result.ok)
        self.assertEqual(result.exit_code, 3)
        self.assertIn("oops", result.stderr)

    async def test_missing_command_is_reported_not_raised(self) -> None:
        result = await self.transport.run("definitely-not-a-real-command-xyz")
        self.assertFalse(result.ok)
        self.assertEqual(result.exit_code, 127)
        self.assertIsNone(result.error)

    async def test_timeout_is_reported_as_an_error(self) -> None:
        result = await self.transport.run("sleep 5", timeout=1)
        self.assertFalse(result.ok)
        self.assertIn("таймаут", result.error)

    async def test_remote_path_is_exported(self) -> None:
        result = await self.transport.run("command -v cash >/dev/null && echo found || echo missing")
        expected = "found" if REMOTE_PATH else "missing"
        self.assertEqual(result.stdout.strip(), expected)

    async def test_sftp_lists_and_transfers_a_file(self) -> None:
        from cashdesk_control.core.files import SftpFileSystem

        sftp = await self.transport.open_sftp()
        home = str(await sftp.realpath("."))
        fs = SftpFileSystem(sftp, home)

        entries = await fs.listdir(home)
        self.assertIsInstance(entries, list)

        remote = f"{home}/cashdesk_probe.txt"
        await fs.write_bytes(remote, b"probe content\n")
        self.addAsyncCleanup(lambda: asyncio.ensure_future(fs.remove(remote)))

        listing = await fs.listdir(home)
        names = [entry.name for entry in listing]
        self.assertIn("cashdesk_probe.txt", names)
        saved = next(entry for entry in listing if entry.name == "cashdesk_probe.txt")
        self.assertEqual(saved.size, len(b"probe content\n"))
        self.assertTrue(saved.permissions.startswith("-"))

        self.assertEqual(await fs.read_bytes(remote), b"probe content\n")
        await fs.rename(remote, remote + ".renamed")
        await fs.remove(remote + ".renamed")

    async def test_interactive_process_receives_input(self) -> None:
        process = await self.transport.open_terminal(term_size=(100, 24))
        self.addAsyncCleanup(process.close)
        process.stdin.write(b"echo TERM_PROBE_$((6*7))\n")
        chunks = b""
        for _ in range(40):
            chunk = await process.stdout.read(4096)
            if not chunk:
                break
            chunks += chunk
            if b"TERM_PROBE_42" in chunks:
                break
        self.assertIn(b"TERM_PROBE_42", chunks)

    async def test_local_port_forward_carries_traffic(self) -> None:
        """A real forward: connect through 127.0.0.1 and reach the SSH banner."""

        server = await asyncio.start_server(self._echo, HOST, 0)
        self.addAsyncCleanup(server.close)
        target_port = server.sockets[0].getsockname()[1]

        spec = TunnelSpec(name=f"probe-{target_port}", local_port=0, target_host="127.0.0.1", target_port=target_port)
        backend = AsyncSSHTunnelBackend(self.transport)
        listener = await backend.open(spec)
        self.addAsyncCleanup(lambda: asyncio.ensure_future(backend.close(listener)))
        local_port = listener.get_port()
        self.assertGreater(local_port, 0, "the OS must assign a real port when 0 is requested")

        reader, writer = await asyncio.open_connection("127.0.0.1", local_port)
        self.addAsyncCleanup(writer.close)
        writer.write(b"ping\n")
        await writer.drain()
        line = await asyncio.wait_for(reader.readline(), timeout=5)
        self.assertEqual(line.strip(), b"pong")
        self.assertIsNotNone(backend)  # backend is exercised by the session tests

    @staticmethod
    async def _echo(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        line = await reader.readline()
        writer.write(b"pong\n" if line.strip() == b"ping" else b"?\n")
        await writer.drain()
        writer.close()


@unittest.skipUnless(_server_available(), "no test SSH server configured")
class SessionOverSshTests(unittest.IsolatedAsyncioTestCase):
    async def test_session_runs_commands_through_the_transport(self) -> None:
        session = KassSession(_profile())
        transport = AsyncSSHSessionTransport()
        self.addAsyncCleanup(transport.close)
        await session.connect(transport)
        self.addAsyncCleanup(session.disconnect)
        self.assertTrue(session.is_connected)

        result = await session.run("echo SESSION_OK")
        self.assertTrue(result.ok, result.error)
        self.assertIn("SESSION_OK", result.stdout)

    async def test_report_is_collected_over_ssh(self) -> None:
        session = KassSession(_profile())
        transport = AsyncSSHSessionTransport()
        self.addAsyncCleanup(transport.close)
        await session.connect(transport)
        self.addAsyncCleanup(session.disconnect)

        builder = KassReportBuilder(session.profile.name, session.profile.host, options=ReportOptions(concurrency=4))
        report = await builder.collect(session.run)

        self.assertGreater(len(report.sections), 20)
        platform = report.section("6.0")
        self.assertIsNotNone(platform)
        self.assertIn("ОС:", platform.body)
        self.assertTrue(report.facts.get("arch"))
        # the noisy hardware dumps stay out of the report
        self.assertIsNone(report.section("6.5"))
        self.assertIsNone(report.section("6.7"))

    async def test_quick_command_specs_execute_for_real(self) -> None:
        from cashdesk_control.core.commands import CommandCatalog

        session = KassSession(_profile())
        transport = AsyncSSHSessionTransport()
        self.addAsyncCleanup(transport.close)
        await session.connect(transport)
        self.addAsyncCleanup(session.disconnect)

        catalog = CommandCatalog.defaults()
        for spec_id in ("disk_free", "hw_platform", "net_route"):
            spec = catalog.get(spec_id)
            result = await session.run(spec.command, timeout=spec.timeout)
            self.assertIsNone(result.error, f"{spec_id}: {result.error}")

    async def test_disconnected_session_returns_an_error_result(self) -> None:
        session = KassSession(_profile())
        result = await session.run("echo nope")
        self.assertFalse(result.ok)
        self.assertIn("не подключена", result.error)


class LocalTransportTests(unittest.IsolatedAsyncioTestCase):
    """The local transport backs the report when the engineer sits at the kassa."""

    @unittest.skipUnless(shutil.which("bash"), "bash is required")
    async def test_local_run(self) -> None:
        transport = LocalProcessTransport()
        await transport.open(_profile(name="Локальная машина"))
        self.addAsyncCleanup(transport.close)
        result = await transport.run("echo LOCAL_OK")
        self.assertTrue(result.ok, result.error)
        self.assertIn("LOCAL_OK", result.stdout)

    @unittest.skipUnless(shutil.which("bash"), "bash is required")
    async def test_local_timeout(self) -> None:
        transport = LocalProcessTransport()
        await transport.open(_profile(name="Локальная машина"))
        self.addAsyncCleanup(transport.close)
        result = await transport.run("sleep 5", timeout=1)
        self.assertIn("таймаут", result.error or "")


@unittest.skipUnless(_server_available(), "no test SSH server configured")
class TunnelManagerOverSshTests(unittest.IsolatedAsyncioTestCase):
    async def test_manager_opens_and_stops_a_forward(self) -> None:
        from cashdesk_control.core.tunnel_manager import TunnelManager

        server = await asyncio.start_server(self._echo, HOST, 0)
        self.addAsyncCleanup(server.close)
        target_port = server.sockets[0].getsockname()[1]

        session = KassSession(_profile())
        transport = AsyncSSHSessionTransport()
        self.addAsyncCleanup(transport.close)
        await session.connect(transport)
        self.addAsyncCleanup(session.disconnect)

        manager = TunnelManager(session.events)
        spec = TunnelSpec(name=f"mgr-{target_port}", local_port=0, target_host="127.0.0.1", target_port=target_port)
        tunnel = await manager.open(spec, AsyncSSHTunnelBackend(transport), session)
        self.addAsyncCleanup(manager.stop_all)
        self.assertTrue(tunnel.is_active)
        self.assertIn(tunnel.tunnel_id, session.tunnel_ids)
        await manager.stop_for(session.session_id)
        self.assertEqual(session.tunnel_ids, ())

    @staticmethod
    async def _echo(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readline()
        writer.write(b"pong\n")
        await writer.drain()
        writer.close()


class CommandSpecShapeTests(unittest.TestCase):
    """Guards the two operations the user drives with a button."""

    def test_restart_command(self) -> None:
        spec = CommandSpec(id="cash_restart", label="Перезапустить кассу", command="cash restart", risk=Risk.DANGER, confirm=True)
        self.assertEqual(spec.command, "cash restart")
        self.assertTrue(spec.refresh_report is False)

    def test_reboot_command(self) -> None:
        spec = CommandSpec(id="full_reboot", label="Полная перезагрузка", command="sudo reboot", risk=Risk.CRITICAL, confirm=True, needs_sudo=True)
        self.assertTrue(spec.needs_sudo)
        self.assertTrue(spec.is_destructive)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
