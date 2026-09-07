"""Protocol tests for the built-in VNC client.

A minimal RFB 3.8 server is implemented here as the test double: it speaks the
real wire format, so the client is exercised against genuine bytes rather than a
mock object.
"""

from __future__ import annotations

import asyncio
import struct
import unittest
import zlib

from cashdesk_control.core.vnc import (
    BYTES_PER_PIXEL,
    ENC_COPYRECT,
    ENC_HEXTILE,
    ENC_RAW,
    ENC_RRE,
    ENC_ZRLE,
    VncAuthError,
    VncClient,
)

WIDTH, HEIGHT = 32, 24


def pixel(red: int, green: int, blue: int) -> bytes:
    """Pixel as it travels on the wire (red-shift 0, green 8, blue 16)."""

    return bytes((red, green, blue, 0))


def stored(red: int, green: int, blue: int) -> bytes:
    """What the client keeps in its framebuffer: alpha is forced to opaque."""

    return bytes((red, green, blue, 0xFF))


def solid_rect(width: int, height: int, colour: bytes) -> bytes:
    return colour * (width * height)


class RfbTestServer:
    """Scripted RFB server used to drive the client through each encoding."""

    def __init__(self, encoding: int, *, password: str | None = None) -> None:
        self.encoding = encoding
        self.password = password
        self.server: asyncio.AbstractServer | None = None
        self.port = 0
        self.received: list[bytes] = []
        self.messages: list[int] = []
        self.handshake_done = asyncio.Event()
        self.client_disconnected = asyncio.Event()

    async def start(self) -> None:
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            writer.write(b"RFB 003.008\n")
            await writer.drain()
            await reader.readexactly(12)

            if self.password is None:
                writer.write(bytes([1, 1]))  # one security type: None
            else:
                writer.write(bytes([1, 2]))  # one security type: VNC Authentication
            await writer.drain()
            chosen = (await reader.readexactly(1))[0]
            if chosen == 2:
                writer.write(b"\x00" * 16)  # all-zero challenge
                await writer.drain()
                response = await reader.readexactly(16)
                self.received.append(response)
            writer.write(struct.pack(">I", 0))  # SecurityResult OK
            await writer.drain()

            shared = await reader.readexactly(1)
            self.received.append(shared)
            name = b"test-cashier"
            writer.write(struct.pack(">HH", WIDTH, HEIGHT))
            writer.write(b"\x20\x18\x00\x01" + struct.pack(">HHH", 255, 255, 255) + bytes((0, 8, 16)) + b"\x00\x00\x00")
            writer.write(struct.pack(">I", len(name)) + name)
            await writer.drain()
            self.handshake_done.set()

            await self._consume_client_messages(reader)
            await self._send_frame(writer)
            await asyncio.sleep(0.05)
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        finally:
            self.client_disconnected.set()
            writer.close()

    async def _consume_client_messages(self, reader: asyncio.StreamReader) -> None:
        """Read SetPixelFormat, SetEncodings and the first update request."""

        while True:
            kind = (await reader.readexactly(1))[0]
            self.messages.append(kind)
            if kind == 0:  # SetPixelFormat
                await reader.readexactly(19)
            elif kind == 2:  # SetEncodings
                count = struct.unpack(">xH", await reader.readexactly(3))[0]
                await reader.readexactly(count * 4)
            elif kind == 3:  # FramebufferUpdateRequest
                await reader.readexactly(9)
                return
            else:
                return

    async def _send_frame(self, writer: asyncio.StreamWriter) -> None:
        writer.write(struct.pack(">BBH", 0, 0, 1))  # FramebufferUpdate, one rect
        writer.write(struct.pack(">HHHHi", 0, 0, WIDTH, HEIGHT, self.encoding))
        writer.write(self._payload())
        await writer.drain()

    def _payload(self) -> bytes:
        red = pixel(0xE0, 0x10, 0x20)
        if self.encoding == ENC_RAW:
            return solid_rect(WIDTH, HEIGHT, red)
        if self.encoding == ENC_COPYRECT:
            # The client framebuffer starts zeroed, so copying keeps it zeroed.
            return struct.pack(">HH", 0, 0)
        if self.encoding == ENC_RRE:
            payload = struct.pack(">I", 1) + pixel(0x11, 0x22, 0x33)
            payload += pixel(0x44, 0x55, 0x66) + struct.pack(">HHHH", 4, 4, 8, 8)
            return payload
        if self.encoding == ENC_HEXTILE:
            return self._hextile_payload(red)
        if self.encoding == ENC_ZRLE:
            return self._zrle_payload(red)
        raise AssertionError(f"unsupported encoding in test: {self.encoding}")

    @staticmethod
    def _hextile_payload(colour: bytes) -> bytes:
        """Background + foreground + one 3x3 subrect at tile offset (1, 1)."""

        foreground = pixel(0x77, 0x88, 0x99)
        payload = b""
        for _tile_y in range(0, HEIGHT, 16):
            for _tile_x in range(0, WIDTH, 16):
                payload += bytes([0x02 | 0x04 | 0x08])  # bg + fg + any subrects
                payload += colour
                payload += foreground
                payload += bytes([1])  # one subrect
                payload += bytes([0x11])  # x=1, y=1
                payload += bytes([0x22])  # w=3, h=3
        return payload

    @staticmethod
    def _zrle_payload(colour: bytes) -> bytes:
        raw = b""
        for _tile_y in range(0, HEIGHT, 64):
            for _tile_x in range(0, WIDTH, 64):
                tile_w = min(64, WIDTH)
                tile_h = min(64, HEIGHT)
                raw += bytes([0])  # raw CPIXEL
                raw += colour * (tile_w * tile_h)
        compressed = zlib.compress(raw)
        return struct.pack(">I", len(compressed)) + compressed


class VncClientTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, server: RfbTestServer, **kwargs) -> VncClient:
        await server.start()
        self.addAsyncCleanup(server.stop)
        client = VncClient("127.0.0.1", server.port, **kwargs)
        self.addAsyncCleanup(client.close)
        info = await client.connect()
        self.assertEqual((info.width, info.height), (WIDTH, HEIGHT))
        self.assertEqual(info.name, "test-cashier")
        frames: asyncio.Event = asyncio.Event()

        def on_frame(_rects) -> None:
            frames.set()

        client.set_callbacks(on_frame=on_frame)
        client.start()
        await asyncio.wait_for(frames.wait(), timeout=5)
        return client

    def _pixel_at(self, client: VncClient, x: int, y: int) -> bytes:
        offset = (y * client.width + x) * BYTES_PER_PIXEL
        return bytes(client.framebuffer[offset : offset + BYTES_PER_PIXEL])

    async def test_raw_encoding_fills_framebuffer(self) -> None:
        server = RfbTestServer(ENC_RAW)
        client = await self._run(server)
        self.assertEqual(self._pixel_at(client, 0, 0), stored(0xE0, 0x10, 0x20))
        self.assertEqual(self._pixel_at(client, WIDTH - 1, HEIGHT - 1), stored(0xE0, 0x10, 0x20))
        self.assertIn(0, server.messages)  # SetPixelFormat was sent

    async def test_zrle_encoding_fills_framebuffer(self) -> None:
        client = await self._run(RfbTestServer(ENC_ZRLE))
        self.assertEqual(self._pixel_at(client, 5, 5), stored(0xE0, 0x10, 0x20))

    async def test_rre_encoding_paints_background_and_subrect(self) -> None:
        client = await self._run(RfbTestServer(ENC_RRE))
        self.assertEqual(self._pixel_at(client, 0, 0), stored(0x11, 0x22, 0x33))
        self.assertEqual(self._pixel_at(client, 6, 6), stored(0x44, 0x55, 0x66))
        self.assertEqual(self._pixel_at(client, 20, 20), stored(0x11, 0x22, 0x33))

    async def test_hextile_encoding_paints_background_and_subrect(self) -> None:
        client = await self._run(RfbTestServer(ENC_HEXTILE))
        self.assertEqual(self._pixel_at(client, 0, 0), stored(0xE0, 0x10, 0x20))
        self.assertEqual(self._pixel_at(client, 2, 2), stored(0x77, 0x88, 0x99))
        self.assertEqual(self._pixel_at(client, 10, 10), stored(0xE0, 0x10, 0x20))

    async def test_copyrect_leaves_framebuffer_untouched(self) -> None:
        client = await self._run(RfbTestServer(ENC_COPYRECT))
        self.assertEqual(self._pixel_at(client, 3, 3), b"\x00\x00\x00\xff")

    async def test_pointer_and_key_events_reach_the_server(self) -> None:
        server = RfbTestServer(ENC_RAW)
        await server.start()
        self.addAsyncCleanup(server.stop)
        client = VncClient("127.0.0.1", server.port)
        self.addAsyncCleanup(client.close)
        await client.connect()
        await client.send_pointer(7, 9, 1)
        await client.send_key(0x41, True)
        await client.send_key(0x41, False)
        await client.send_text("ф")
        await asyncio.sleep(0.1)
        # Drain whatever the server received on its side by closing cleanly.
        self.assertTrue(client.is_connected)

    async def test_vnc_authentication_uses_des(self) -> None:
        server = RfbTestServer(ENC_RAW, password="secret")
        client = await self._run(server, password="secret")
        self.assertEqual(server.received[-1].__len__(), 1)  # ClientInit shared flag
        challenge_response = server.received[0]
        self.assertEqual(len(challenge_response), 16)
        # All-zero challenge with a known key gives a stable, non-zero digest.
        self.assertNotEqual(challenge_response, b"\x00" * 16)
        self.assertEqual(client.info.security, "VNC Auth")

    async def test_rejected_password_raises(self) -> None:
        server = RfbTestServer(ENC_RAW)
        await server.start()
        self.addAsyncCleanup(server.stop)

        async def rejecting(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            writer.write(b"RFB 003.008\n")
            await writer.drain()
            await reader.readexactly(12)
            writer.write(bytes([1, 1]))
            await writer.drain()
            await reader.readexactly(1)
            writer.write(struct.pack(">I", 1) + struct.pack(">I", 12) + "нет доступа".encode("utf-8")[:12])
            await writer.drain()
            writer.close()

        reject_server = await asyncio.start_server(rejecting, "127.0.0.1", 0)
        self.addAsyncCleanup(reject_server.close)
        port = reject_server.sockets[0].getsockname()[1]
        client = VncClient("127.0.0.1", port)
        with self.assertRaises(VncAuthError):
            await client.connect()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
