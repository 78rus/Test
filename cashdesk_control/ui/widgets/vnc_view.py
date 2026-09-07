"""VNC surface: blits the RFB framebuffer and forwards mouse/keyboard."""

from __future__ import annotations

import logging
from typing import Any

from ...core.asyncio_utils import schedule
from ...core.vnc import Rect, VncClient

try:
    from PySide6.QtCore import QPoint, Qt, QTimer, Signal
    from PySide6.QtGui import QImage, QPainter, QPixmap
    from PySide6.QtWidgets import (
        QComboBox,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QVBoxLayout,
        QWidget,
    )
except ImportError:  # pragma: no cover
    QT_AVAILABLE = False
else:
    QT_AVAILABLE = True

logger = logging.getLogger("cashdesk_control.vnc")

#: Qt key → X11 keysym for the keys a cashier session actually needs.
_SPECIAL_KEYSYMS = {
    "Backspace": 0xFF08,
    "Tab": 0xFF09,
    "Return": 0xFF0D,
    "Enter": 0xFF0D,
    "Escape": 0xFF1B,
    "Delete": 0xFFFF,
    "Home": 0xFF50,
    "Left": 0xFF51,
    "Up": 0xFF52,
    "Right": 0xFF53,
    "Down": 0xFF54,
    "PageUp": 0xFF55,
    "PageDown": 0xFF56,
    "End": 0xFF57,
    "Insert": 0xFF63,
    "F1": 0xFFBE, "F2": 0xFFBF, "F3": 0xFFC0, "F4": 0xFFC1,
    "F5": 0xFFC2, "F6": 0xFFC3, "F7": 0xFFC4, "F8": 0xFFC5,
    "F9": 0xFFC6, "F10": 0xFFC7, "F11": 0xFFC8, "F12": 0xFFC9,
    "Shift": 0xFFE1, "Control": 0xFFE3, "Alt": 0xFFE9, "AltGr": 0xFFEA,
    "Meta": 0xFFEB, "CapsLock": 0xFFE5,
    "Print": 0xFF61, "Pause": 0xFF13,
}


if QT_AVAILABLE:

    class VncSurface(QWidget):
        """The remote desktop, scaled to the available space."""

        pointerEvent = Signal(int, int, int)
        keyEvent = Signal(int, bool)
        surfaceSize = Signal(int, int)

        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.setMouseTracking(True)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self.setMinimumSize(320, 240)
            self._pixmap: QPixmap | None = None
            self._buttons = 0
            self._scale = 1.0
            self._offset = QPoint(0, 0)
            self._stretch = True
            self._dirty_rects: list[Rect] = []
            self._timer = QTimer(self)
            self._timer.setSingleShot(True)
            self._timer.timeout.connect(self._flush)

        def set_framebuffer(self, buffer: bytearray, width: int, height: int) -> None:
            if width <= 0 or height <= 0 or len(buffer) < width * height * 4:
                return
            image = QImage(bytes(buffer), width, height, width * 4, QImage.Format.Format_RGBA8888)
            self._pixmap = QPixmap.fromImage(image.copy())
            self._apply_geometry()
            self.surfaceSize.emit(width, height)

        def set_stretch(self, enabled: bool) -> None:
            self._stretch = enabled
            self._apply_geometry()

        def _apply_geometry(self) -> None:
            if self._pixmap is None:
                return
            if self._stretch:
                self.setMinimumSize(self._pixmap.size().scaled(320, 240, Qt.AspectRatioMode.KeepAspectRatio))
            self.update()

        def update_rects(self, rects: list[Rect]) -> None:
            self._dirty_rects.extend(rects)
            if not self._timer.isActive():
                self._timer.start(33)

        def _flush(self) -> None:
            self._dirty_rects.clear()
            self.update()

        def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
            painter = QPainter(self)
            painter.fillRect(self.rect(), Qt.GlobalColor.black)
            if self._pixmap is None:
                painter.setPen(Qt.GlobalColor.white)
                painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Нет изображения")
                painter.end()
                return
            target = self._target_rect()
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, not self._stretch)
            painter.drawPixmap(target, self._pixmap)
            painter.end()

        def _target_rect(self):
            from PySide6.QtCore import QRect

            if self._pixmap is None:
                return QRect(0, 0, 0, 0)
            if self._stretch:
                return QRect(0, 0, self.width(), self.height())
            size = self._pixmap.size()
            if size.width() <= self.width() and size.height() <= self.height():
                return QRect((self.width() - size.width()) // 2, (self.height() - size.height()) // 2, size.width(), size.height())
            scaled = size.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
            return QRect((self.width() - scaled.width()) // 2, (self.height() - scaled.height()) // 2, scaled.width(), scaled.height())

        def _to_remote(self, position: QPoint) -> tuple[int, int]:
            if self._pixmap is None:
                return 0, 0
            target = self._target_rect()
            if target.width() <= 0 or target.height() <= 0:
                return 0, 0
            scale_x = self._pixmap.width() / target.width()
            scale_y = self._pixmap.height() / target.height()
            x = int((position.x() - target.x()) * scale_x)
            y = int((position.y() - target.y()) * scale_y)
            return max(0, min(x, self._pixmap.width() - 1)), max(0, min(y, self._pixmap.height() - 1))

        # -- input -------------------------------------------------------------
        def mouseMoveEvent(self, event) -> None:  # noqa: N802
            x, y = self._to_remote(event.position().toPoint())
            self.pointerEvent.emit(x, y, self._buttons)

        def mousePressEvent(self, event) -> None:  # noqa: N802
            self.setFocus()
            self._buttons |= _button_mask(event.button())
            x, y = self._to_remote(event.position().toPoint())
            self.pointerEvent.emit(x, y, self._buttons)

        def mouseReleaseEvent(self, event) -> None:  # noqa: N802
            self._buttons &= ~_button_mask(event.button())
            x, y = self._to_remote(event.position().toPoint())
            self.pointerEvent.emit(x, y, self._buttons)

        def wheelEvent(self, event) -> None:  # noqa: N802
            delta = event.angleDelta().y()
            button = 4 if delta > 0 else 5
            x, y = self._to_remote(event.position().toPoint())
            self.pointerEvent.emit(x, y, self._buttons | (1 << (button - 1)))
            self.pointerEvent.emit(x, y, self._buttons)

        def keyPressEvent(self, event) -> None:  # noqa: N802
            keysym = _keysym_for(event)
            if keysym is None:
                super().keyPressEvent(event)
                return
            self.keyEvent.emit(keysym, True)
            event.accept()

        def keyReleaseEvent(self, event) -> None:  # noqa: N802
            keysym = _keysym_for(event)
            if keysym is None:
                super().keyReleaseEvent(event)
                return
            self.keyEvent.emit(keysym, False)
            event.accept()

    class VncViewer(QWidget):
        """Connection controls plus the remote desktop surface."""

        stateChanged = Signal(str)
        fatal = Signal(str)

        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self._client: VncClient | None = None
            self._task: asyncio.Task[Any] | None = None
            layout = QVBoxLayout(self)
            layout.setContentsMargins(10, 10, 10, 10)
            layout.setSpacing(8)

            bar = QHBoxLayout()
            bar.setSpacing(6)
            self.status = QLabel("не подключено", objectName="dim")
            bar.addWidget(self.status)
            bar.addStretch()
            self.fit_combo = QComboBox()
            self.fit_combo.addItems(["Вписать в окно", "Реальный размер"])
            self.fit_combo.currentIndexChanged.connect(self._mode_changed)
            bar.addWidget(self.fit_combo)
            self.send_ctrl_alt_del = QPushButton("Ctrl+Alt+Del", objectName="secondary")
            self.send_ctrl_alt_del.clicked.connect(self._send_cad)
            bar.addWidget(self.send_ctrl_alt_del)
            self.refresh = QPushButton("Обновить кадр", objectName="secondary")
            self.refresh.clicked.connect(self._force_update)
            bar.addWidget(self.refresh)
            self.disconnect_button = QPushButton("Отключить", objectName="secondary")
            self.disconnect_button.clicked.connect(lambda: schedule(self.disconnect()))
            self.disconnect_button.setEnabled(False)
            bar.addWidget(self.disconnect_button)
            layout.addLayout(bar)

            self.surface = VncSurface()
            self.surface.pointerEvent.connect(self._on_pointer)
            self.surface.keyEvent.connect(self._on_key)
            self.surface.surfaceSize.connect(self._on_size)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(self.surface)
            layout.addWidget(scroll, 1)

        async def connect_to(self, host: str, port: int, password: str | None = None, *, shared: bool = True) -> None:
            await self.disconnect()
            client = VncClient(host, port, password, shared=shared)
            self._client = client
            self.status.setText(f"подключение к {host}:{port}…")
            self.stateChanged.emit("connecting")
            try:
                info = await client.connect()
            except Exception as exc:
                self._client = None
                message = str(exc) or exc.__class__.__name__
                self.status.setText(f"ошибка: {message}")
                self.stateChanged.emit("error")
                self.fatal.emit(message)
                return
            client.set_callbacks(
                on_frame=self.surface.update_rects,
                on_name=self._on_name,
                on_closed=self._on_closed,
            )
            client.start()
            self.status.setText(f"{info.name} · {info.width}×{info.height} · {info.security}")
            self.stateChanged.emit("connected")
            self.disconnect_button.setEnabled(True)

        async def disconnect(self) -> None:
            client, self._client = self._client, None
            if client is not None:
                await client.close()
            self.disconnect_button.setEnabled(False)
            self.status.setText("не подключено")
            self.stateChanged.emit("disconnected")

        def _on_pointer(self, x: int, y: int, buttons: int) -> None:
            client = self._client
            if client is None:
                return
            schedule(client.send_pointer(x, y, buttons))

        def _on_key(self, keysym: int, down: bool) -> None:
            client = self._client
            if client is None:
                return
            schedule(client.send_key(keysym, down))

        def _on_size(self, width: int, height: int) -> None:
            client = self._client
            if client is None:
                return
            client.width, client.height = width, height
            if len(client.framebuffer) < width * height * 4:
                buffer = bytearray(width * height * 4)
                for index in range(3, len(buffer), 4):
                    buffer[index] = 0xFF
                client.framebuffer = buffer
            self.surface.set_framebuffer(client.framebuffer, width, height)

        def _on_name(self, name: str) -> None:
            self.status.setText(name)

        def _on_closed(self, reason: str | None) -> None:
            self._client = None
            self.disconnect_button.setEnabled(False)
            self.status.setText(f"соединение закрыто: {reason}" if reason else "соединение закрыто")
            self.stateChanged.emit("disconnected")

        def _force_update(self) -> None:
            client = self._client
            if client is None:
                return
            schedule(client.request_update(incremental=False))
            self._refresh_image()

        def _refresh_image(self) -> None:
            client = self._client
            if client is not None:
                self.surface.set_framebuffer(client.framebuffer, client.width, client.height)

        def _mode_changed(self, index: int) -> None:
            self.surface.set_stretch(index == 0)

        def _send_cad(self) -> None:
            client = self._client
            if client is None:
                return

            async def sequence() -> None:
                for keysym in (0xFFE3, 0xFFE9, 0xFFFF):
                    await client.send_key(keysym, True)
                for keysym in (0xFFFF, 0xFFE9, 0xFFE3):
                    await client.send_key(keysym, False)

            schedule(sequence())

    def keysym_for_character(character: str) -> int:
        """X11 keysym for a character: Latin-1 directly, Unicode via 0x01000000."""

        code = ord(character)
        return code if code < 0x100 else 0x01000000 | code

    def _button_mask(button) -> int:
        from PySide6.QtCore import Qt

        if button == Qt.MouseButton.LeftButton:
            return 1
        if button == Qt.MouseButton.MiddleButton:
            return 2
        if button == Qt.MouseButton.RightButton:
            return 4
        return 0

    def _keysym_for(event) -> int | None:
        name = event.key()
        key_name = _key_name(name)
        if key_name in _SPECIAL_KEYSYMS:
            return _SPECIAL_KEYSYMS[key_name]
        text = event.text()
        if text and len(text) == 1:
            return keysym_for_character(text)
        return None

    def _key_name(key: int) -> str:
        from PySide6.QtCore import Qt

        for name in _SPECIAL_KEYSYMS:
            attribute = getattr(Qt.Key, f"Key_{name}", None)
            if attribute == key:
                return name
        return ""

else:

    class VncViewer:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PySide6 is required for the VNC viewer")
