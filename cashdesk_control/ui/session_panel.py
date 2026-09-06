"""Sidebar widgets for active cashier sessions."""

from __future__ import annotations

from typing import Iterable

from ..core.models import SessionSnapshot, SessionState

try:
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget
except ImportError:  # pragma: no cover - optional Qt dependency.
    QT_AVAILABLE = False
else:
    QT_AVAILABLE = True


if QT_AVAILABLE:

    class SessionRow(QPushButton):
        def __init__(self, snapshot: SessionSnapshot, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.snapshot = snapshot
            self.setObjectName("session")
            self.setCheckable(True)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            layout = QHBoxLayout(self)
            layout.setContentsMargins(8, 5, 8, 5)
            layout.setSpacing(8)
            initials = QLabel(snapshot.name[:1].upper())
            initials.setFixedSize(29, 29)
            initials.setAlignment(Qt.AlignmentFlag.AlignCenter)
            initials.setStyleSheet("QLabel { color: #b7c3ff; background: #273568; border-radius: 7px; font-weight: 750; }")
            copy = QVBoxLayout()
            copy.setSpacing(1)
            name = QLabel(snapshot.name, objectName="sessionName")
            meta = QLabel(snapshot.host, objectName="sessionMeta")
            copy.addWidget(name)
            copy.addWidget(meta)
            status_name, status_object = _status_text(snapshot.state)
            status = QLabel(status_name, objectName=status_object)
            status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            layout.addWidget(initials)
            layout.addLayout(copy, 1)
            layout.addWidget(status)

        def update_snapshot(self, snapshot: SessionSnapshot) -> None:
            self.snapshot = snapshot


    class SessionPanel(QFrame):
        sessionSelected = Signal(str)
        newConnectionRequested = Signal()

        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setObjectName("sidebar")
            self.setMinimumWidth(245)
            self.setMaximumWidth(285)
            self._rows: dict[str, SessionRow] = {}
            self._selected_id: str | None = None

            layout = QVBoxLayout(self)
            layout.setContentsMargins(14, 20, 14, 14)
            layout.setSpacing(10)
            brand = QHBoxLayout()
            brand.setContentsMargins(7, 0, 7, 0)
            mark = QLabel("▰▰▰")
            mark.setStyleSheet("QLabel { color: #8da5ff; font-size: 13px; letter-spacing: -3px; }")
            lockup = QVBoxLayout()
            lockup.setSpacing(0)
            lockup.addWidget(QLabel("КАССА", objectName="brand"))
            lockup.addWidget(QLabel("CONTROL", objectName="brandSub"))
            brand.addWidget(mark)
            brand.addLayout(lockup)
            brand.addStretch()
            layout.addLayout(brand)

            workspace = QFrame(objectName="panel")
            workspace_layout = QHBoxLayout(workspace)
            workspace_layout.setContentsMargins(9, 7, 9, 7)
            workspace_layout.setSpacing(8)
            avatar = QLabel("ОЦ")
            avatar.setFixedSize(29, 29)
            avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
            avatar.setStyleSheet("QLabel { color: #d4dcff; background: #384d9a; border-radius: 7px; font-size: 10px; font-weight: 750; }")
            workspace_copy = QVBoxLayout()
            workspace_copy.setSpacing(1)
            workspace_copy.addWidget(QLabel("Рабочее пространство", objectName="dim"))
            workspace_copy.addWidget(QLabel("Операционный центр", objectName="sessionName"))
            workspace_layout.addWidget(avatar)
            workspace_layout.addLayout(workspace_copy)
            layout.addWidget(workspace)

            new_button = QPushButton("＋  Новое подключение", objectName="primary")
            new_button.setCursor(Qt.CursorShape.PointingHandCursor)
            new_button.clicked.connect(lambda: self.newConnectionRequested.emit())
            layout.addWidget(new_button)

            layout.addWidget(QLabel("РАБОЧАЯ ОБЛАСТЬ", objectName="eyebrow"))
            nav_sessions = QPushButton("▦  Все сессии   ·   0", objectName="nav")
            nav_sessions.setCheckable(True)
            nav_sessions.setChecked(True)
            nav_sessions.setEnabled(False)
            layout.addWidget(nav_sessions)
            activity = QPushButton("⌁  Журнал событий", objectName="nav")
            activity.clicked.connect(lambda: self.parent_window_message("Журнал событий будет подключён к EventBus."))
            layout.addWidget(activity)
            profiles = QPushButton("▣  Сохранённые профили", objectName="nav")
            profiles.clicked.connect(lambda: self.parent_window_message("Профили хранятся без паролей в ProfileStore."))
            layout.addWidget(profiles)

            heading = QHBoxLayout()
            heading.addWidget(QLabel("АКТИВНЫЕ СЕССИИ", objectName="eyebrow"))
            heading.addStretch()
            heading.addWidget(QLabel("10 слотов", objectName="dim"))
            layout.addLayout(heading)
            self.list_widget = QListWidget(objectName="sessionList")
            self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.list_widget.setSpacing(3)
            self.list_widget.itemClicked.connect(self._item_clicked)
            layout.addWidget(self.list_widget, 1)

            secure = QFrame(objectName="panel")
            secure_layout = QHBoxLayout(secure)
            secure_layout.setContentsMargins(8, 7, 8, 7)
            secure_layout.setSpacing(7)
            secure_layout.addWidget(QLabel("◆", objectName="statusOnline"))
            secure_copy = QVBoxLayout()
            secure_copy.setSpacing(1)
            secure_copy.addWidget(QLabel("Хранилище защищено", objectName="sessionName"))
            secure_copy.addWidget(QLabel("Ключи в системном keyring", objectName="dim"))
            secure_layout.addLayout(secure_copy)
            layout.addWidget(secure)

        def set_sessions(self, snapshots: Iterable[SessionSnapshot], active_id: str | None) -> None:
            self.list_widget.clear()
            self._rows.clear()
            for snapshot in snapshots:
                row = SessionRow(snapshot)
                row.clicked.connect(lambda session_id=snapshot.session_id: self.sessionSelected.emit(session_id))
                item = QListWidgetItem()
                item.setSizeHint(row.sizeHint())
                self.list_widget.addItem(item)
                self.list_widget.setItemWidget(item, row)
                self._rows[snapshot.session_id] = row
            self.set_active(active_id)

        def set_active(self, session_id: str | None) -> None:
            self._selected_id = session_id
            for key, row in self._rows.items():
                row.setChecked(key == session_id)

        def update_session(self, snapshot: SessionSnapshot) -> None:
            row = self._rows.get(snapshot.session_id)
            if row:
                row.update_snapshot(snapshot)

        def parent_window_message(self, message: str) -> None:
            window = self.window()
            if hasattr(window, "show_status"):
                window.show_status(message)

        def _item_clicked(self, item: QListWidgetItem) -> None:
            row = self.list_widget.itemWidget(item)
            if row:
                self.sessionSelected.emit(row.snapshot.session_id)

else:

    class SessionPanel:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PySide6 is required for the desktop session panel")


def _status_text(state: SessionState) -> tuple[str, str]:
    if state is SessionState.CONNECTED:
        return "● online", "statusOnline"
    if state in {SessionState.CONNECTING, SessionState.DEGRADED}:
        return "● checking", "statusWarning"
    if state is SessionState.ERROR:
        return "● error", "statusWarning"
    return "● offline", "statusOffline"
