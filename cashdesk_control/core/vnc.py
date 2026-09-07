"""A pure-Python RFB 3.8 client for the built-in VNC viewer.

The viewer avoids Qt WebEngine and ``websockify``: fewer moving parts, a smaller
Windows build, and the framebuffer ends up in a plain :class:`bytearray` the Qt
widget can blit directly. Supported encodings are ZRLE, Hextile, RRE, CopyRect
and Raw — the intersection that x11vnc, TigerVNC, RealVNC and TightVNC all
implement. Security types ``None`` and ``VNC Authentication`` are supported.

The module has no Qt import, so the protocol can be exercised by the test-suite
against a scripted server.
"""

from __future__ import annotations

import asyncio
import logging
import struct
import zlib
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

logger = logging.getLogger("cashdesk_control.vnc")

# Encodings ------------------------------------------------------------------
ENC_RAW = 0
ENC_COPYRECT = 1
ENC_RRE = 2
ENC_HEXTILE = 5
ENC_TIGHT = 7
ENC_ZRLE = 16
ENC_CURSOR = -239
ENC_LAST_RECT = -224
ENC_DESKTOP_NAME = -307

SUPPORTED_ENCODINGS: tuple[int, ...] = (ENC_ZRLE, ENC_HEXTILE, ENC_COPYRECT, ENC_RRE, ENC_RAW)

# Pixel format we ask the server for: 32bpp, memory order R,G,B,_ so the buffer
# maps straight onto QImage.Format_RGBA8888 with the last byte forced to 0xFF.
PIXEL_FORMAT = struct.pack(
    ">BBBBHHHBBBxxx",
    32,  # bits-per-pixel
    24,  # depth
    0,  # big-endian-flag
    1,  # true-colour-flag
    255,  # red-max
    255,  # green-max
    255,  # blue-max
    0,  # red-shift
    8,  # green-shift
    16,  # blue-shift
)
BYTES_PER_PIXEL = 4


@dataclass(slots=True)
class ServerInfo:
    width: int
    height: int
    name: str
    security: str = "None"
    protocol: str = "RFB 003.008"
    pixel_format: bytes = field(default=b"", repr=False)


@dataclass(slots=True)
class Rect:
    x: int
    y: int
    width: int
    height: int
    encoding: int


class VncError(RuntimeError):
    """Raised when the remote end breaks the RFB protocol."""


class VncAuthError(VncError):
    """Raised when the server rejects the VNC password."""


def _des_encrypt(challenge: bytes, password: str) -> bytes:
    """RFB VNC authentication: DES-ECB with a bit-reversed key.

    Single DES is expressed as 3DES with K1=K2=K3, which is the standard way to
    reach the legacy cipher through ``cryptography``.
    """

    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, modes

        try:  # cryptography >= 48 moved the legacy algorithms
            from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
        except ImportError:  # pragma: no cover - older cryptography
            from cryptography.hazmat.primitives.ciphers.algorithms import TripleDES
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise VncError("для VNC-пароля нужен пакет 'cryptography'") from exc
    raw = password.encode("latin-1", "replace")[:8].ljust(8, b"\x00")
    key = bytes(int(f"{byte:08b}"[::-1], 2) for byte in raw)
    cipher = Cipher(TripleDES(key * 3), modes.ECB())
    encryptor = cipher.encryptor()
    return encryptor.update(challenge) + encryptor.finalize()


class VncClient:
    """One VNC connection. Feed events in, receive framebuffer updates."""

    def __init__(
        self,
        host: str,
        port: int = 5900,
        password: str | None = None,
        *,
        shared: bool = True,
        name: str = "",
        connect_timeout: float = 15.0,
    ) -> None:
        self.host = host
        self.port = port
        self.password = password
        self.shared = shared
        self.name = name
        self.connect_timeout = connect_timeout
        self.info: ServerInfo | None = None
        self.framebuffer: bytearray = bytearray()
        self.width = 0
        self.height = 0
        self.cursor: tuple[int, int, bytes, bytes] | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._closed = False
        self._dirty: list[Rect] = []
        self._reader_task: asyncio.Task[Any] | None = None
        self._update_pending = False
        self._on_frame: Callable[[list[Rect]], None] | None = None
        self._on_bell: Callable[[], None] | None = None
        self._on_name: Callable[[str], None] | None = None
        self._on_closed: Callable[[str | None], None] | None = None

    # -- callbacks -----------------------------------------------------------
    def set_callbacks(
        self,
        *,
        on_frame: Callable[[list[Rect]], None] | None = None,
        on_bell: Callable[[], None] | None = None,
        on_name: Callable[[str], None] | None = None,
        on_closed: Callable[[str | None], None] | None = None,
    ) -> None:
        self._on_frame = on_frame
        self._on_bell = on_bell
        self._on_name = on_name
        self._on_closed = on_closed

    @property
    def is_connected(self) -> bool:
        return self._writer is not None and not self._closed

    # -- handshake -----------------------------------------------------------
    async def connect(self) -> ServerInfo:
        """Perform the RFB handshake and leave the connection ready for updates."""

        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port), timeout=self.connect_timeout
        )
        reader = self._reader
        assert reader is not None
        version = await self._read_exact(12)
        if not version.startswith(b"RFB "):
            raise VncError(f"ожидался ответ RFB, получено: {version!r}")
        protocol = version.decode("latin-1").strip()
        await self._write(b"RFB 003.008\n")

        security = await self._negotiate_security(reader)
        info = await self._client_init(reader, protocol, security)
        self.info = info
        self.width, self.height = info.width, info.height
        self.framebuffer = bytearray(info.width * info.height * BYTES_PER_PIXEL)
        for index in range(3, len(self.framebuffer), BYTES_PER_PIXEL):
            self.framebuffer[index] = 0xFF

        # SetPixelFormat: message-type (1) + padding (3) + pixel-format (16).
        await self._write(b"\x00\x00\x00\x00" + PIXEL_FORMAT)
        await self._set_encodings(SUPPORTED_ENCODINGS + (ENC_CURSOR, ENC_DESKTOP_NAME, ENC_LAST_RECT))
        await self.request_update(incremental=False)
        return info

    async def _negotiate_security(self, reader: asyncio.StreamReader) -> str:
        count_byte = await self._read_exact(1)
        count = count_byte[0]
        if count == 0:
            message = await self._read_exact(4)
            length = struct.unpack(">I", message)[0]
            reason = (await self._read_exact(length)).decode("utf-8", "replace") if length else "без описания"
            raise VncError(f"сервер отклонил подключение: {reason}")
        types = list(await self._read_exact(count))
        chosen = next((kind for kind in (1, 2) if kind in types), None)
        if chosen is None:
            raise VncError(f"неподдерживаемые типы безопасности: {types}")
        await self._write(bytes([chosen]))
        if chosen == 2:
            challenge = await self._read_exact(16)
            await self._write(_des_encrypt(challenge, self.password or ""))
        result = struct.unpack(">I", await self._read_exact(4))[0]
        if result != 0:
            reason = ""
            try:
                length = struct.unpack(">I", await self._read_exact(4))[0]
                reason = (await self._read_exact(length)).decode("utf-8", "replace")
            except (VncError, asyncio.IncompleteReadError):
                pass
            raise VncAuthError(reason or "сервер отклонил пароль VNC")
        return "VNC Auth" if chosen == 2 else "None"

    async def _client_init(self, reader: asyncio.StreamReader, protocol: str, security: str) -> ServerInfo:
        await self._write(bytes([1 if self.shared else 0]))
        header = await self._read_exact(24)
        width, height = struct.unpack(">HH", header[:4])
        pixel_format = header[4:20]
        name_length = struct.unpack(">I", header[20:24])[0]
        name = (await self._read_exact(name_length)).decode("utf-8", "replace") if name_length else self.host
        if width <= 0 or height <= 0:
            raise VncError(f"некорректный размер экрана: {width}x{height}")
        return ServerInfo(width=width, height=height, name=name, security=security, protocol=protocol, pixel_format=pixel_format)

    async def _set_encodings(self, encodings: Iterable[int]) -> None:
        values = list(encodings)
        payload = struct.pack(">BxH", 2, len(values)) + b"".join(struct.pack(">i", value) for value in values)
        await self._write(payload)

    # -- main loop -----------------------------------------------------------
    def start(self) -> None:
        """Begin reading server messages until the connection drops."""

        if self._reader_task is None or self._reader_task.done():
            self._reader_task = asyncio.ensure_future(self._read_loop())

    async def wait_closed(self) -> None:
        if self._reader_task is not None:
            await self._reader_task

    async def _read_loop(self) -> None:
        error: str | None = None
        try:
            while self.is_connected:
                message_type = (await self._read_exact(1))[0]
                if message_type == 0:
                    await self._handle_framebuffer_update()
                elif message_type == 1:
                    await self._handle_colour_map()
                elif message_type == 2:
                    if self._on_bell:
                        self._on_bell()
                elif message_type == 3:
                    await self._handle_cut_text()
                else:
                    raise VncError(f"неизвестный тип сообщения сервера: {message_type}")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            error = str(exc) or exc.__class__.__name__
            if not self._closed:
                logger.warning("vnc read loop stopped: %s", error)
        finally:
            self._closed = True
            if self._on_closed:
                self._on_closed(error)

    async def _handle_framebuffer_update(self) -> None:
        header = await self._read_exact(3)
        count = struct.unpack(">xH", header)[0]
        self._dirty = []
        for _ in range(count):
            rect_header = await self._read_exact(12)
            x, y, width, height, encoding = struct.unpack(">HHHHi", rect_header)
            rect = Rect(x, y, width, height, encoding)
            if encoding == ENC_LAST_RECT:
                break
            if encoding == ENC_DESKTOP_NAME:
                await self._handle_desktop_name(width)
                continue
            await self._decode_rect(rect)
            self._dirty.append(rect)
        if self._dirty and self._on_frame:
            self._on_frame(list(self._dirty))

    async def _handle_desktop_name(self, length: int) -> None:
        name = (await self._read_exact(length)).decode("utf-8", "replace")
        if self.info is not None:
            self.info.name = name
        if self._on_name:
            self._on_name(name)

    async def _handle_colour_map(self) -> None:
        header = await self._read_exact(5)
        _, count = struct.unpack(">xHH", header)
        await self._read_exact(count * 6)

    async def _handle_cut_text(self) -> None:
        header = await self._read_exact(7)
        length = struct.unpack(">xxxI", header)[0]
        await self._read_exact(length)

    # -- rectangle decoding ---------------------------------------------------
    async def _decode_rect(self, rect: Rect) -> None:
        if rect.width <= 0 or rect.height <= 0:
            return
        if rect.encoding == ENC_RAW:
            await self._decode_raw(rect)
        elif rect.encoding == ENC_COPYRECT:
            await self._decode_copyrect(rect)
        elif rect.encoding == ENC_RRE:
            await self._decode_rre(rect)
        elif rect.encoding == ENC_HEXTILE:
            await self._decode_hextile(rect)
        elif rect.encoding == ENC_ZRLE:
            await self._decode_zrle(rect)
        elif rect.encoding == ENC_CURSOR:
            await self._decode_cursor(rect)
        else:
            raise VncError(f"неподдерживаемое кодирование: {rect.encoding}")

    def _blit(self, rect: Rect, data: bytes, source_stride: int | None = None) -> None:
        """Copy decoded RGBA rows into the framebuffer, clipping to the screen."""

        stride = source_stride or rect.width * BYTES_PER_PIXEL
        x0, y0 = max(rect.x, 0), max(rect.y, 0)
        x1 = min(rect.x + rect.width, self.width)
        y1 = min(rect.y + rect.height, self.height)
        if x1 <= x0 or y1 <= y0:
            return
        width = (x1 - x0) * BYTES_PER_PIXEL
        offset = (y0 - rect.y) * stride + (x0 - rect.x) * BYTES_PER_PIXEL
        target_stride = self.width * BYTES_PER_PIXEL
        for row in range(y1 - y0):
            start = offset + row * stride
            chunk = data[start : start + width]
            if len(chunk) < width:
                chunk = chunk + b"\x00" * (width - len(chunk))
            destination = (y0 + row) * target_stride + x0 * BYTES_PER_PIXEL
            self.framebuffer[destination : destination + width] = chunk

    def _fill(self, rect: Rect, pixel: bytes) -> None:
        row = (pixel[:3] + b"\xff") * rect.width
        self._blit(rect, row * rect.height)

    async def _decode_raw(self, rect: Rect) -> None:
        data = bytearray(await self._read_exact(rect.width * rect.height * BYTES_PER_PIXEL))
        self._normalise_alpha(data)
        self._blit(rect, bytes(data))

    async def _decode_copyrect(self, rect: Rect) -> None:
        source = await self._read_exact(4)
        src_x, src_y = struct.unpack(">HH", source)
        stride = self.width * BYTES_PER_PIXEL
        rows = []
        for row in range(rect.height):
            start = (src_y + row) * stride + src_x * BYTES_PER_PIXEL
            rows.append(bytes(self.framebuffer[start : start + rect.width * BYTES_PER_PIXEL]))
        self._blit(rect, b"".join(rows))

    async def _decode_rre(self, rect: Rect) -> None:
        header = await self._read_exact(4 + BYTES_PER_PIXEL)
        background = header[4:]
        count = struct.unpack(">I", header[:4])[0]
        self._fill(rect, background)
        for _ in range(count):
            item = await self._read_exact(BYTES_PER_PIXEL + 8)
            pixel = item[:BYTES_PER_PIXEL]
            sub_x, sub_y, sub_w, sub_h = struct.unpack(">HHHH", item[BYTES_PER_PIXEL:])
            sub = Rect(rect.x + sub_x, rect.y + sub_y, sub_w, sub_h, ENC_RAW)
            self._fill(sub, pixel)

    async def _decode_hextile(self, rect: Rect) -> None:
        background = b"\x00\x00\x00\xff"
        foreground = b"\xff\xff\xff\xff"
        for tile_y in range(rect.y, rect.y + rect.height, 16):
            for tile_x in range(rect.x, rect.x + rect.width, 16):
                tile_w = min(16, rect.x + rect.width - tile_x)
                tile_h = min(16, rect.y + rect.height - tile_y)
                tile = Rect(tile_x, tile_y, tile_w, tile_h, ENC_HEXTILE)
                flags = (await self._read_exact(1))[0]
                if flags & 0x01:  # raw
                    data = bytearray(await self._read_exact(tile_w * tile_h * BYTES_PER_PIXEL))
                    self._normalise_alpha(data)
                    self._blit(tile, bytes(data))
                    continue
                if flags & 0x02:
                    background = self._alpha(await self._read_exact(BYTES_PER_PIXEL))
                if flags & 0x04:
                    foreground = self._alpha(await self._read_exact(BYTES_PER_PIXEL))
                self._fill(tile, background)
                if not flags & 0x08:
                    continue
                subrect_count = (await self._read_exact(1))[0]
                coloured = bool(flags & 0x10)
                for _ in range(subrect_count):
                    if coloured:
                        pixel = self._alpha(await self._read_exact(BYTES_PER_PIXEL))
                    else:
                        pixel = foreground
                    xy, wh = await self._read_exact(2)
                    sub_x, sub_y = xy >> 4, xy & 0x0F
                    sub_w, sub_h = (wh >> 4) + 1, (wh & 0x0F) + 1
                    self._fill(Rect(tile_x + sub_x, tile_y + sub_y, sub_w, sub_h, ENC_HEXTILE), pixel)

    async def _decode_zrle(self, rect: Rect) -> None:
        length = struct.unpack(">I", await self._read_exact(4))[0]
        compressed = await self._read_exact(length)
        data = zlib.decompress(compressed)
        position = 0
        for tile_y in range(rect.y, rect.y + rect.height, 64):
            for tile_x in range(rect.x, rect.x + rect.width, 64):
                tile_w = min(64, rect.x + rect.width - tile_x)
                tile_h = min(64, rect.y + rect.height - tile_y)
                subencoding = data[position]
                position += 1
                position = self._zrle_tile(data, position, Rect(tile_x, tile_y, tile_w, tile_h, ENC_ZRLE), subencoding)

    def _zrle_tile(self, data: bytes, position: int, tile: Rect, subencoding: int) -> int:
        pixels = tile.width * tile.height
        if subencoding == 0:  # raw CPIXEL
            raw = data[position : position + pixels * BYTES_PER_PIXEL]
            position += pixels * BYTES_PER_PIXEL
            buffer = bytearray(raw)
            self._normalise_alpha(buffer)
            self._blit(tile, bytes(buffer))
            return position
        if subencoding == 1:  # solid
            pixel = self._alpha(data[position : position + BYTES_PER_PIXEL])
            position += BYTES_PER_PIXEL
            self._fill(tile, pixel)
            return position
        if 2 <= subencoding <= 16:  # packed palette
            palette_size = subencoding
            palette, position = self._zrle_palette(data, position, palette_size)
            bits = {2: 1, 3: 2, 4: 2, 5: 3, 6: 3, 7: 3, 8: 3}.get(palette_size, 4)
            buffer = bytearray()
            for row in range(tile.height):
                bit_position = 0
                row_bytes = data[position : position + ((tile.width * bits + 7) // 8)]
                position += len(row_bytes)
                accumulator = 0
                available = 0
                for column in range(tile.width):
                    while available < bits:
                        accumulator = (accumulator << 8) | row_bytes[bit_position]
                        bit_position += 1
                        available += 8
                    available -= bits
                    index = (accumulator >> available) & ((1 << bits) - 1)
                    buffer += palette[min(index, len(palette) - 1)]
                self._blit(Rect(tile.x, tile.y + row, tile.width, 1, ENC_ZRLE), bytes(buffer))
                buffer = bytearray()
            return position
        if subencoding == 128:  # plain RLE
            buffer = bytearray()
            remaining = pixels
            while remaining > 0:
                pixel = self._alpha(data[position : position + BYTES_PER_PIXEL])
                position += BYTES_PER_PIXEL
                run = 1
                while True:
                    byte = data[position]
                    position += 1
                    run += byte
                    if byte != 255:
                        break
                buffer += pixel * min(run, remaining)
                remaining -= run
            self._blit(tile, bytes(buffer))
            return position
        if 129 <= subencoding <= 255:  # palette RLE
            palette_size = subencoding - 128
            palette, position = self._zrle_palette(data, position, palette_size)
            buffer = bytearray()
            remaining = pixels
            while remaining > 0:
                index = data[position]
                position += 1
                run = 1
                if index & 0x80:
                    index &= 0x7F
                    while True:
                        byte = data[position]
                        position += 1
                        run += byte
                        if byte != 255:
                            break
                buffer += palette[min(index, len(palette) - 1)] * min(run, remaining)
                remaining -= run
            self._blit(tile, bytes(buffer))
            return position
        raise VncError(f"неподдерживаемый ZRLE subencoding: {subencoding}")

    def _zrle_palette(self, data: bytes, position: int, size: int) -> tuple[list[bytes], int]:
        palette = []
        for _ in range(size):
            palette.append(self._alpha(data[position : position + BYTES_PER_PIXEL]))
            position += BYTES_PER_PIXEL
        return palette, position

    async def _decode_cursor(self, rect: Rect) -> None:
        pixel_bytes = rect.width * rect.height * BYTES_PER_PIXEL
        mask_bytes = ((rect.width + 7) // 8) * rect.height
        pixels = await self._read_exact(pixel_bytes)
        mask = await self._read_exact(mask_bytes)
        self.cursor = (rect.width, rect.height, pixels, mask)

    # -- client messages -------------------------------------------------------
    async def request_update(self, *, incremental: bool = True, x: int = 0, y: int = 0, width: int | None = None, height: int | None = None) -> None:
        if not self.is_connected:
            return
        payload = struct.pack(
            ">BBHHHH",
            3,
            1 if incremental else 0,
            x,
            y,
            width or self.width,
            height or self.height,
        )
        await self._write(payload)

    async def send_key(self, keysym: int, down: bool) -> None:
        if not self.is_connected:
            return
        await self._write(struct.pack(">BBxxI", 4, 1 if down else 0, keysym))

    async def send_text(self, text: str) -> None:
        for character in text:
            code = ord(character)
            # X11 keysym: Latin-1 as-is, anything else via the Unicode range.
            keysym = code if code < 0x100 else 0x01000000 | code
            await self.send_key(keysym, True)
            await self.send_key(keysym, False)

    async def send_pointer(self, x: int, y: int, buttons: int) -> None:
        if not self.is_connected:
            return
        await self._write(struct.pack(">BBHH", 5, buttons, max(0, min(x, self.width - 1)), max(0, min(y, self.height - 1))))

    async def send_clipboard(self, text: str) -> None:
        if not self.is_connected:
            return
        encoded = text.encode("latin-1", "replace")
        await self._write(struct.pack(">BxxxI", 6, len(encoded)) + encoded)

    # -- plumbing ---------------------------------------------------------------
    @staticmethod
    def _alpha(pixel: bytes) -> bytes:
        return bytes(pixel[:3]) + b"\xff"

    @staticmethod
    def _normalise_alpha(data: Any) -> None:
        for index in range(3, len(data), BYTES_PER_PIXEL):
            data[index] = 0xFF

    async def _read_exact(self, count: int) -> bytes:
        if self._reader is None:
            raise VncError("соединение не установлено")
        if count == 0:
            return b""
        data = await self._reader.readexactly(count)
        return data

    async def _write(self, payload: bytes) -> None:
        if self._writer is None or self._closed:
            return
        self._writer.write(payload)
        await self._writer.drain()

    async def close(self) -> None:
        self._closed = True
        if self._reader_task is not None and not self._reader_task.done():
            self._reader_task.cancel()
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception as exc:  # pragma: no cover - best effort
                logger.debug("vnc close warning: %s", exc)
            self._writer = None
        self._reader = None


__all__ = [
    "BYTES_PER_PIXEL",
    "SUPPORTED_ENCODINGS",
    "Rect",
    "ServerInfo",
    "VncAuthError",
    "VncClient",
    "VncError",
]
