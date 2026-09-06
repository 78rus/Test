from __future__ import annotations

import asyncio
import unittest

from cashdesk_control.core.models import ConnectionProfile, SessionState, TunnelSpec
from cashdesk_control.core.session import KassSession, SessionConnectionError
from cashdesk_control.core.session_manager import SessionLimitError, SessionManager
from cashdesk_control.core.tunnel import TunnelState
from cashdesk_control.core.tunnel_manager import TunnelConflictError, TunnelManager


class FakeTransport:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.opened = False
        self.closed = False

    async def open(self, profile: ConnectionProfile) -> None:
        await asyncio.sleep(0)
        if self.fail:
            raise OSError("connection refused")
        self.opened = True

    async def close(self) -> None:
        await asyncio.sleep(0)
        self.closed = True


class FakeBackend:
    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.opens = 0
        self.closes = 0

    async def open(self, spec: TunnelSpec) -> object:
        self.opens += 1
        await asyncio.sleep(0)
        if self.opens <= self.failures:
            raise OSError("jump host unavailable")
        return object()

    async def close(self, handle: object) -> None:
        self.closes += 1
        await asyncio.sleep(0)


def profile(name: str = "Склад · Терминал 01", profile_id: str = "warehouse") -> ConnectionProfile:
    return ConnectionProfile(name=name, host="10.24.8.41", username="operator", profile_id=profile_id)


class SessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_session_lifecycle_and_snapshot(self) -> None:
        session = KassSession(profile())
        transport = FakeTransport()
        await session.connect(transport)

        self.assertEqual(session.state, SessionState.CONNECTED)
        self.assertTrue(session.snapshot().connected_at)
        await session.disconnect()
        self.assertEqual(session.state, SessionState.DISCONNECTED)
        self.assertTrue(transport.closed)

    async def test_connection_failure_is_reported_and_state_is_error(self) -> None:
        session = KassSession(profile())
        with self.assertRaises(SessionConnectionError):
            await session.connect(FakeTransport(fail=True))
        self.assertEqual(session.state, SessionState.ERROR)
        self.assertEqual(session.snapshot().last_error, "connection refused")


class SessionManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_limit_activation_and_remove(self) -> None:
        manager = SessionManager(max_sessions=2)
        first = manager.create(profile())
        second = manager.create(profile("Кафе · Касса 02", "cafe"))
        self.assertEqual(manager.active_id, first.session_id)
        manager.activate(second.session_id)
        self.assertIs(manager.active_session, second)
        with self.assertRaises(SessionLimitError):
            manager.create(profile("Третий терминал", "third"))
        await manager.remove(second.session_id)
        self.assertEqual(manager.active_id, first.session_id)

    async def test_close_all_disconnects_every_transport(self) -> None:
        manager = SessionManager(max_sessions=2)
        first = manager.create(profile())
        second = manager.create(profile("Кафе", "cafe"))
        first_transport, second_transport = FakeTransport(), FakeTransport()
        await first.connect(first_transport)
        await second.connect(second_transport)
        await manager.close_all()
        self.assertEqual(len(manager), 0)
        self.assertTrue(first_transport.closed)
        self.assertTrue(second_transport.closed)


class TunnelTests(unittest.IsolatedAsyncioTestCase):
    async def test_port_conflict_is_rejected_before_network_call(self) -> None:
        manager = TunnelManager()
        spec = TunnelSpec("postgres", 55432, "127.0.0.1", 5432)
        manager.add(spec, FakeBackend())
        with self.assertRaises(TunnelConflictError):
            manager.add(TunnelSpec("postgres-copy", 55432, "127.0.0.1", 5432), FakeBackend())

    async def test_auto_restart_after_transport_loss(self) -> None:
        backend = FakeBackend()
        manager = TunnelManager()
        tunnel = manager.add(
            TunnelSpec("vnc", 55901, "127.0.0.1", 5901, reconnect_delay=0.01),
            backend,
        )
        await tunnel.start()
        self.assertEqual(tunnel.state, TunnelState.ACTIVE)
        await tunnel.mark_lost("channel closed")
        self.assertEqual(tunnel.state, TunnelState.RECONNECTING)
        await asyncio.sleep(0.03)
        self.assertEqual(tunnel.state, TunnelState.ACTIVE)
        self.assertEqual(backend.opens, 2)
        await tunnel.stop()
        self.assertEqual(tunnel.state, TunnelState.STOPPED)


if __name__ == "__main__":
    unittest.main()
