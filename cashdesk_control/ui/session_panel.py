"""Sidebar with the active cashier sessions."""

from __future__ import annotations

from typing import Iterable

from .. import __version__
from ..core.models import SessionSnapshot, SessionState

try:
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtWidgets import (
        QFrame,
        QHBoxLayout,
        QLabel,
        QListWidget,
        QListWidgetItem,
        QPushButton,
        QSizePolicy,
        QVBoxLayout,
        QWidget,
    )
except ImportError:  # pragma: no cover - optional Qt dependency.
    QT_AVAILABLE = False
else:
    QT_AVAILABLE = True


SESSION_COLORS = {
    "blue": "#4d7cfe",
    "violet": "#9b6ef3",
    "amber": "#e8a33d",
    "green": "#2fb583",
    "slate": "#64748b",
    "rose": "#e05c7a",
}

MAX_SESSIONS = 10


if QT_AVAILABLE:

    class SessionRow(QPushButton):
        """One session card in the sidebar."""

        def __init__(self, snapshot: SessionSnapshot, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setCheckable(True)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            layout = QHBoxLayout(self)
            layout.setContentsMargins(8, 6, 8, 6)
            layout.setSpacing(8)

            self.badge = QLabel(snapshot.name[:1].upper())
            self.badge.setFixedSize(30, 30)
            self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.badge.setStyleSheet(
                f"QLabel {{ color: #ffffff;"
                f" background: {SESSION_COLORS.get(snapshot.color, '#4d7cfe')};"
                " border-radius: 8px; font-weight: 750; }"
            )
            layout.addWidget(self.badge)

            copy = QVBoxLayout()
            copy.setSpacing(2)
            self.name = QLabel(snapshot.name, objectName="sessionName")
            self.meta = QLabel("", objectName="sessionMeta")
            copy.addWidget(self.name)
            copy.addWidget(self.meta)
            layout.addLayout(copy, 1)

            self.status = QLabel("")
            self.status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            layout.addWidget(self.status)
            self.update_snapshot(snapshot)

        def update_snapshot(self, snapshot: SessionSnapshot) -> None:
            self.snapshot = snapshot
            self.name.setText(snapshot.name)
            details = [part for part in (snapshot.host, snapshot.kass_type) if part and part != "Не определена"]
            if snapshot.version:
                details.append(f"v{snapshot.version}")
            self.meta.setText(" · ".join(details) or snapshot.host)
            label, style = _status_text(snapshot.state)
            self.status.setText(label)
            self.status.setObjectName(style)
            self.status.style().unpolish(self.status)
            self.status.style().polish(self.status)
            tooltip = snapshot.name
            if snapshot.last_error:
                tooltip += f"\n{snapshot.last_error}"
            if snapshot.facts.get("module_state"):
                tooltip += f"\nКассовый модуль: {snapshot.facts['module_state']}"
            self.setToolTip(tooltip)

    class SessionPanel(QFrame):
        """Sidebar: brand, new-connection button and the session list."""

        sessionSelected = Signal(str)
        newConnectionRequested = Signal()
        reportRequested = Signal()
        profilesRequested = Signal()

        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setObjectName("sidebar")
            self.setMinimumWidth(250)
            self.setMaximumWidth(300)
            self._rows: dict[str, SessionRow] = {}
            self._selected_id: str | None = None

            layout = QVBoxLayout(self)
            layout.setContentsMargins(14, 18, 14, 12)
            layout.setSpacing(10)

            brand = QHBoxLayout()
            brand.setContentsMargins(6, 0, 6, 0)
            brand.setSpacing(8)
            mark = QLabel("▰▰▰")
            mark.setStyleSheet("QLabel { color: #5b8cff; font-size: 13px; letter-spacing: -3px; }")
            lockup = QVBoxLayout()
            lockup.setSpacing(0)
            lockup.addWidget(QLabel("КАССА", objectName="brand"))
            self.version_label = QLabel(f"CONTROL · v{__version__}", objectName="brandSub")
            lockup.addWidget(self.version_label)
            brand.addWidget(mark)
            brand.addLayout(lockup)
            brand.addStretch()
            layout.addLayout(brand)

            new_button = QPushButton("＋  Новое подключение")
            new_button.setObjectName("primary")
            new_button.setCursor(Qt.CursorShape.PointingHandCursor)
            new_button.clicked.connect(self.newConnectionRequested.emit)
            layout.addWidget(new_button)

            layout.addWidget(QLabel("ИНСТРУМЕНТЫ", objectName="eyebrow"))
            report = QPushButton("▤  Сводный отчёт по кассе")
            report.setObjectName("nav")
            report.clicked.connect(self.reportRequested.emit)
            layout.addWidget(report)
            profiles = QPushButton("⚙  Сохранённые профили")
            profiles.setObjectName("nav")
            profiles.clicked.connect(self.profilesRequested.emit)
            layout.addWidget(profiles)

            heading = QHBoxLayout()
            heading.addWidget(QLabel("АКТИВНЫЕ СЕССИИ", objectName="eyebrow"))
            heading.addStretch()
            self.counter = QLabel("0 / 10", objectName="dim")
            heading.addWidget(self.counter)
            layout.addLayout(heading)

            self.list_widget = QListWidget(objectName="sessionList")
            self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.list_widget.setSpacing(4)
            self.list_widget.itemClicked.connect(self._item_clicked)
            layout.addWidget(self.list_widget, 1)

            self.placeholder = QLabel(
                "Сессий нет.\nДобавьте кассу кнопкой выше\nили Ctrl+N.",
                objectName="dim",
            )
            self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.placeholder.setWordWrap(True)
            layout.addWidget(self.placeholder)

        def set_sessions(self, snapshots: Iterable[SessionSnapshot], active_id: str | None) -> None:
            self.list_widget.clear()
            self._rows.clear()
            items = list(snapshots)
            for snapshot in items:
                row = SessionRow(snapshot)
                row.clicked.connect(lambda session_id=snapshot.session_id: self.sessionSelected.emit(session_id))
                item = QListWidgetItem()
                item.setSizeHint(row.sizeHint())
                self.list_widget.addItem(item)
                self.list_widget.setItemWidget(item, row)
                self._rows[snapshot.session_id] = row
            self.counter.setText(f"{len(items)} / {MAX_SESSIONS}")
            self.placeholder.setVisible(not items)
            self.list_widget.setVisible(bool(items))
            self.set_active(active_id)

        def set_active(self, session_id: str | None) -> None:
            self._selected_id = session_id
            for key, row in self._rows.items():
                row.setChecked(key == session_id)

        def update_session(self, snapshot: SessionSnapshot) -> None:
            row = self._rows.get(snapshot.session_id)
            if row:
                row.update_snapshot(snapshot)

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
        return "● онлайн", "statusOnline"
    if state is SessionState.CONNECTING:
        return "● подключение", "statusWarning"
    if state is SessionState.DEGRADED:
        return "● деградация", "statusWarning"
    if state is SessionState.ERROR:
        return "● ошибка", "statusError"
    if state is SessionState.CLOSING:
        return "● закрытие", "statusOffline"
    return "● офлайн", "statusOffline"
