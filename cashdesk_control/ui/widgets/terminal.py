"""Interactive SSH terminal: pyte emulation rendered with QPainter.

The widget is a real PTY client — it sends keystrokes to the cashier and paints
whatever the remote shell sends back, including colours, cursor movement and
alternate screens used by ``top`` or ``less``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

try:  # Qt is optional for core-only deployments.
    from PySide6.QtCore import Qt, QRect, Signal, QTimer
    from PySide6.QtGui import (
        QColor,
        QFont,
        QFontDatabase,
        QFontMetrics,
        QPainter,
        QPen,
        QTextCursor,
    )
    from PySide6.QtWidgets import (
        QApplication,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QSizePolicy,
        QVBoxLayout,
        QWidget,
    )
except ImportError:  # pragma: no cover - exercised only when optional Qt is absent.
    QT_AVAILABLE = False
else:
    QT_AVAILABLE = True

logger = logging.getLogger("cashdesk_control.terminal")

try:
    import pyte
except ImportError:  # pragma: no cover
    pyte = None


_NAMED_COLORS = {
    "black": "#000000",
    "red": "#cd3131",
    "green": "#0dbc79",
    "brown": "#a3851c",
    "yellow": "#e5e510",
    "blue": "#2472c8",
    "magenta": "#bc3fbc",
    "cyan": "#11a8cd",
    "white": "#c8c8c8",
    "brightblack": "#666666",
    "brightred": "#f14c4c",
    "brightgreen": "#23d18b",
    "brightbrown": "#f5f543",
    "brightyellow": "#f5f543",
    "brightblue": "#3b8eea",
    "brightmagenta": "#d670d6",
    "brightcyan": "#29b8db",
    "brightwhite": "#e5e5e5",
    "default": None,
}


def _color(value: Any, default: str) -> str:
    if value in ("default", None, ""):
        return default
    if isinstance(value, int):
        return _palette(value)
    text = str(value)
    if text.isdigit():
        return _palette(int(text))
    return _NAMED_COLORS.get(text.lower(), default)


def _palette(index: int) -> str:
    if index < 16:
        names = (
            "black", "red", "green", "brown", "blue", "magenta", "cyan", "white",
            "brightblack", "brightred", "brightgreen", "brightyellow",
            "brightblue", "brightmagenta", "brightcyan", "brightwhite",
        )
        return _NAMED_COLORS[names[index]]
    if index < 232:
        value = index - 16
        blue = (value % 6) * 51
        green = ((value // 6) % 6) * 51
        red = (value // 36) * 51
        return f"#{red:02x}{green:02x}{blue:02x}"
    grey = 8 + (index - 232) * 10
    return f"#{grey:02x}{grey:02x}{grey:02x}"


if QT_AVAILABLE:

    class TerminalView(QWidget):
        """Paints a pyte screen and forwards keystrokes to the SSH process."""

        sizeChanged = Signal(int, int)
        closed = Signal(str)

        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.setMinimumSize(320, 160)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
            font = QFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
            font.setPointSizeF(10.0)
            font.setStyleHint(QFont.StyleHint.TypeWriter)
            self._font = font
            self._metrics = QFontMetrics(font)
            self._columns = 100
            self._rows = 28
            self._screen: Any = None
            self._stream: Any = None
            self._reader_task: asyncio.Task[Any] | None = None
            self._process: Any = None
            self._closing = False
            self._background = QColor("#0a0d12")
            self._foreground = QColor("#d6dde8")
            self._char_size = self._measure()
            self._repaint_scheduled = False
            self._timer = QTimer(self)
            self._timer.setSingleShot(True)
            self._timer.timeout.connect(self._flush_repaint)
            self.set_screen(self._columns, self._rows)

        # -- pyte ------------------------------------------------------------
        def set_screen(self, columns: int, rows: int) -> None:
            if pyte is None:
                raise RuntimeError("терминал требует пакет 'pyte'")
            columns = max(20, min(columns, 400))
            rows = max(5, min(rows, 200))
            if self._screen is not None and (columns, rows) == (self._columns, self._rows):
                return
            previous = self._screen.display if self._screen is not None else []
            self._columns, self._rows = columns, rows
            self._screen = pyte.Screen(columns, rows)
            # LNM makes a bare "\n" move the cursor to the next line as well,
            # which is what remote command output relies on.
            self._screen.set_mode(pyte.modes.LNM)
            self._stream = pyte.ByteStream(self._screen)
            for line in previous[-rows:]:
                self._stream.feed((line.rstrip() + "\n").encode("utf-8", "replace"))
            self.update()

        def _measure(self) -> tuple[int, int]:
            width = max(6, self._metrics.horizontalAdvance("M"))
            height = max(10, self._metrics.height())
            return width, height

        def resizeEvent(self, event) -> None:  # noqa: N802 - Qt naming
            super().resizeEvent(event)
            char_width, char_height = self._char_size
            if char_width <= 0 or char_height <= 0:
                return
            columns = max(20, (self.width() - 12) // char_width)
            rows = max(5, (self.height() - 12) // char_height)
            if (columns, rows) != (self._columns, self._rows):
                self.set_screen(columns, rows)
                self.sizeChanged.emit(columns, rows)

        def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
            if self._screen is None:
                return
            painter = QPainter(self)
            painter.fillRect(self.rect(), self._background)
            painter.setFont(self._font)
            char_width, char_height = self._char_size
            left_pad, top_pad = 6, 6
            buffer = self._screen.buffer
            for row in range(min(self._rows, len(buffer))):
                line = buffer[row]
                x = 0
                while x < self._columns:
                    char = line.get(x)
                    if char is None:
                        x += 1
                        continue
                    span_text = char.data or " "
                    span_end = x + 1
                    while span_end < self._columns:
                        following = line.get(span_end)
                        if following is None or not _same_style(char, following):
                            break
                        span_text += following.data or " "
                        span_end += 1
                    foreground = _color(char.fg, self._foreground.name())
                    background = _color(char.bg, self._background.name())
                    if char.reverse:
                        foreground, background = background, foreground
                    target = QRect(left_pad + x * char_width, top_pad + row * char_height, char_width * (span_end - x), char_height)
                    if background != self._background.name():
                        painter.fillRect(target, QColor(background))
                    painter.setPen(QColor(foreground))
                    font = self._font
                    if char.bold or char.underscore:
                        font = QFont(self._font)
                        font.setBold(bool(char.bold))
                        font.setUnderline(bool(char.underscore))
                        painter.setFont(font)
                    painter.drawText(target, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, span_text)
                    if char.bold or char.underscore:
                        painter.setFont(self._font)
                    x = span_end
            cursor = self._screen.cursor
            cursor_rect = QRect(left_pad + cursor.x * char_width, top_pad + cursor.y * char_height, char_width, char_height)
            painter.fillRect(cursor_rect, QColor(self._foreground))
            painter.end()

        # -- session wiring ---------------------------------------------------
        async def attach(self, process: Any) -> None:
            """Start rendering *process* (an AsyncSSH interactive process)."""

            await self.detach()
            self._process = process
            self._closing = False
            self._reader_task = asyncio.ensure_future(self._read_loop(process))

        async def detach(self) -> None:
            if self._reader_task is not None and not self._reader_task.done():
                self._reader_task.cancel()
            self._reader_task = None
            process, self._process = self._process, None
            if process is not None:
                try:
                    process.close()
                except Exception as exc:  # pragma: no cover - best effort
                    logger.debug("terminal close warning: %s", exc)

        async def _read_loop(self, process: Any) -> None:
            try:
                while True:
                    chunk = await process.stdout.read(65536)
                    if not chunk:
                        break
                    data = chunk if isinstance(chunk, bytes) else chunk.encode("utf-8", "replace")
                    self._stream.feed(data)
                    self._schedule_repaint()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if not self._closing:
                    self._feed_line(f"\r\n[соединение закрыто: {exc}]\r\n")
            finally:
                if not self._closing:
                    self.closed.emit("канал закрыт")

        def _feed_line(self, text: str) -> None:
            if self._stream is None:
                return
            self._stream.feed(text.encode("utf-8", "replace"))
            self._schedule_repaint()

        def _schedule_repaint(self) -> None:
            """Coalesce bursts of output into at most one repaint per ~16 ms."""

            if self._repaint_scheduled:
                return
            self._repaint_scheduled = True
            self._timer.start(16)

        def _flush_repaint(self) -> None:
            self._repaint_scheduled = False
            self.update()

        # -- input -------------------------------------------------------------
        def send_text(self, text: str) -> None:
            if self._process is None:
                self._feed_line("\r\n[нет подключения]\r\n")
                return
            self._process.stdin.write(text.encode("utf-8", "replace"))

        def send_line(self, command: str) -> None:
            self.send_text(command + "\n")

        def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt naming
            if self._process is None:
                super().keyPressEvent(event)
                return
            sequence = _key_to_bytes(event)
            if sequence is None:
                super().keyPressEvent(event)
                return
            self.send_text(sequence)
            event.accept()

        def write(self, data: bytes) -> None:
            self._stream.feed(data)
            self._schedule_repaint()

        def copy_selection(self) -> None:
            text = self.render_text()
            QApplication.clipboard().setText(text)

        def paste_clipboard(self) -> None:
            text = QApplication.clipboard().text()
            if text:
                self.send_text(text)

        def render_text(self) -> str:
            if self._screen is None:
                return ""
            return "\n".join(self._screen.display).rstrip("\n")

    def _same_style(left: Any, right: Any) -> bool:
        return (
            left.fg == right.fg
            and left.bg == right.bg
            and left.bold == right.bold
            and left.reverse == right.reverse
            and left.underscore == right.underscore
        )

    _CONTROL_KEYS = {
        Qt.Key.Key_Backspace: b"\x7f",
        Qt.Key.Key_Tab: b"\t",
        Qt.Key.Key_Return: b"\r",
        Qt.Key.Key_Enter: b"\r",
        Qt.Key.Key_Escape: b"\x1b",
        Qt.Key.Key_Up: b"\x1b[A",
        Qt.Key.Key_Down: b"\x1b[B",
        Qt.Key.Key_Right: b"\x1b[C",
        Qt.Key.Key_Left: b"\x1b[D",
        Qt.Key.Key_Home: b"\x1bOH",
        Qt.Key.Key_End: b"\x1bOF",
        Qt.Key.Key_PageUp: b"\x1b[5~",
        Qt.Key.Key_PageDown: b"\x1b[6~",
        Qt.Key.Key_Insert: b"\x1b[2~",
        Qt.Key.Key_Delete: b"\x1b[3~",
        Qt.Key.Key_F1: b"\x1bOP",
        Qt.Key.Key_F2: b"\x1bOQ",
        Qt.Key.Key_F3: b"\x1bOR",
        Qt.Key.Key_F4: b"\x1bOS",
        Qt.Key.Key_F5: b"\x1b[15~",
        Qt.Key.Key_F6: b"\x1b[17~",
        Qt.Key.Key_F7: b"\x1b[18~",
        Qt.Key.Key_F8: b"\x1b[19~",
        Qt.Key.Key_F9: b"\x1b[20~",
        Qt.Key.Key_F10: b"\x1b[21~",
        Qt.Key.Key_F11: b"\x1b[23~",
        Qt.Key.Key_F12: b"\x1b[24~",
    }

    def _key_to_bytes(event) -> bytes | None:
        modifiers = event.modifiers()
        key = event.key()
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            text = event.text()
            if text and ord(text[0]) >= 97:
                return bytes([ord(text[0]) - 96])
            if key == Qt.Key.Key_Space:
                return b"\x00"
            if key in (Qt.Key.Key_BracketLeft,):
                return b"\x1b"
        if key in _CONTROL_KEYS:
            return _CONTROL_KEYS[key]
        text = event.text()
        if text:
            return text.encode("utf-8", "replace")
        return None

    class TerminalWidget(QWidget):
        """Terminal surface plus an input line and session status."""

        commandSent = Signal(str)
        disconnected = Signal(str)

        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(10, 10, 10, 10)
            layout.setSpacing(8)

            self.view = TerminalView()
            self.view.closed.connect(self.disconnected.emit)
            layout.addWidget(self.view, 1)

            controls = QHBoxLayout()
            controls.setSpacing(6)
            self.status = QLabel("не подключено", objectName="dim")
            controls.addWidget(self.status)
            controls.addStretch()
            paste = QPushButton("Вставить", objectName="secondary")
            paste.clicked.connect(self.view.paste_clipboard)
            controls.addWidget(paste)
            clear = QPushButton("Очистить", objectName="secondary")
            clear.clicked.connect(self.clear)
            controls.addWidget(clear)
            layout.addLayout(controls)

            row = QHBoxLayout()
            row.setSpacing(6)
            self.input = QLineEdit()
            self.input.setPlaceholderText("Команда для отправки в сессию…")
            self.input.returnPressed.connect(self.submit)
            send = QPushButton("Отправить ↵", objectName="primary")
            send.clicked.connect(self.submit)
            row.addWidget(self.input, 1)
            row.addWidget(send)
            layout.addLayout(row)

        async def attach(self, process: Any, banner: str = "") -> None:
            await self.view.attach(process)
            self.status.setText(banner or "подключено")
            self.input.setEnabled(True)

        async def detach(self) -> None:
            await self.view.detach()
            self.status.setText("не подключено")
            self.input.setEnabled(False)

        def submit(self) -> None:
            command = self.input.text()
            self.input.clear()
            self.view.send_line(command)
            self.commandSent.emit(command)

        def clear(self) -> None:
            self.view.write(b"\x1b[2J\x1b[H")

        def render_text(self) -> str:
            return self.view.render_text()

else:

    class TerminalWidget:  # type: ignore[no-redef]
        """Import-safe placeholder when PySide6 is not installed."""

        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PySide6 is required for the desktop terminal widget")
