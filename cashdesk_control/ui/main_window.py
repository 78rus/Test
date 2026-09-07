"""PySide6 desktop shell: real SSH sessions, commands, VNC, SQL and reports."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..adapters.asyncssh_adapter import AsyncSSHSessionTransport, AsyncSSHTunnelBackend
from ..adapters.credentials import default_store
from ..adapters.keyring_store import KeyringCredentialStore
from ..core.commands import CommandCatalog, CommandSpec, Risk
from ..core.db_client import DatabaseClient
from ..core.detector import classify, hardware_summary
from ..core.files import SftpFileSystem
from ..core.models import ConnectionProfile, SessionSnapshot, SessionState, TunnelSpec
from ..core.paths import app_paths
from ..core.profiles import ProfileStore
from ..core.report import KassReport, KassReportBuilder, ReportOptions
from ..core.session import SessionConnectionError
from ..core.session_manager import SessionLimitError, SessionManager
from ..core.settings import SettingsStore
from ..core.tunnel import SSHTunnel, TunnelState
from ..core.tunnel_manager import TunnelManager

try:  # Keep the core importable when the optional desktop dependencies are absent.
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QAction, QKeySequence
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QDockWidget,
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMessageBox,
        QPlainTextEdit,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QStackedWidget,
        QStatusBar,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )
    from .connection_dialog import ConnectionDialog
    from .report_dock import ReportDock
    from .session_panel import SessionPanel
    from .themes import THEMES, get_theme, qss_for
    from .widgets.file_browser import FileManagerWidget
    from .widgets.logs_page import LogsPage
    from .widgets.settings_page import SettingsPage
    from .widgets.sql_console import SqlConsoleWidget
    from .widgets.terminal import TerminalWidget
    from .widgets.vnc_view import VncViewer
except ImportError:  # pragma: no cover - this path is expected on core-only CI.
    QT_AVAILABLE = False
    THEMES = {}
else:
    QT_AVAILABLE = True


if QT_AVAILABLE:

    class MainWindow(QMainWindow):
        """Application window bound to the real core services."""

        MODULES = ("overview", "terminal", "files", "database", "vnc", "logs", "settings")
        MODULE_LABELS = {
            "overview": "▦  Обзор",
            "terminal": "〉_  Консоль",
            "files": "▱  Файлы",
            "database": "▤  База данных",
            "vnc": "▣  VNC",
            "logs": "☰  Логи",
            "settings": "⚙  Настройки",
        }

        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setWindowTitle("Касса Control — операционный центр")
            self.setMinimumSize(1180, 720)
            self.resize(1520, 900)
            self._logger = logging.getLogger("cashdesk_control")
            self._paths = app_paths().ensure()

            self._settings = SettingsStore(self._paths.settings_file)
            try:
                self._settings.load()
            except Exception as exc:
                self._logger.warning("settings could not be loaded: %s", exc)

            profile_settings = SettingsStore(self._paths.profiles_file)
            try:
                profile_settings.load()
            except Exception as exc:
                self._logger.warning("profiles could not be loaded: %s", exc)
            self._profile_settings = profile_settings
            self._profile_store = ProfileStore(profile_settings)

            self.credentials = default_store(self._paths.config_dir / "secrets.vault")
            self.session_manager = SessionManager(max_sessions=10)
            self.tunnel_manager = TunnelManager(self.session_manager.events)
            self.catalog = CommandCatalog.load(self._paths.config_dir / "commands.json")

            self._transports: dict[str, Any] = {}
            self._tasks: set[asyncio.Task[Any]] = set()
            self._tab_buttons: dict[str, QPushButton] = {}
            self._reports: dict[str, KassReport] = {}
            self._db_clients: dict[str, DatabaseClient] = {}
            self._closing = False

            self._apply_theme(str(self._settings.get("theme", "dark")))
            self._restore_profiles()
            self._build_ui()
            self._subscribe_to_core()
            self._refresh_sessions()
            self._select_session(self.session_manager.active_id)
            self.show_status(
                f"Хранилище секретов: {self.credentials.backend} · профили: {len(self._profile_store.all())}"
            )

        # ==================================================================
        # helpers
        # ==================================================================
        def _spawn(self, coro: Any) -> asyncio.Task[Any] | None:
            """Schedule *coro* on the running loop, keeping a strong reference."""

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                self._logger.error("no event loop; install qasync to enable connections")
                self.show_status("Нет событийного цикла — установите qasync")
                coro.close()
                return None
            task = loop.create_task(coro)
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
            return task

        def _apply_theme(self, key: str) -> None:
            theme = get_theme(key)
            self.setStyleSheet(qss_for(theme.key))
            self._settings.set("theme", theme.key)
            try:
                self._settings.save()
            except Exception as exc:
                self._logger.warning("theme could not be persisted: %s", exc)
            if hasattr(self, "theme_combo"):
                self.theme_combo.blockSignals(True)
                self.theme_combo.setCurrentText(theme.label)
                self.theme_combo.blockSignals(False)
            if hasattr(self, "settings_page"):
                self.settings_page.set_themes(THEMES, theme.key)

        def show_status(self, message: str) -> None:
            if hasattr(self, "_status_label"):
                self._status_label.setText(message)
            self.statusBar().showMessage(message, 8000)

        def log(self, message: str, *, level: str = "info") -> None:
            stamp = datetime.now().strftime("%H:%M:%S")
            colour = {"ok": "#3fc99a", "warn": "#e8b15c", "error": "#f2647c"}.get(level)
            if hasattr(self, "journal") and colour:
                self.journal.appendHtml(
                    f'<span style="color:#68748a">{stamp}</span> <span style="color:{colour}">{_escape(message)}</span>'
                )
            elif hasattr(self, "journal"):
                self.journal.appendPlainText(f"{stamp}  {message}")
            if hasattr(self, "logs_page"):
                self.logs_page.append(message, level=level)
            getattr(self._logger, level if level in ("info", "warning", "error") else "info")(message)

        # ==================================================================
        # UI construction
        # ==================================================================
        def _build_ui(self) -> None:
            root = QWidget(objectName="root")
            root_layout = QHBoxLayout(root)
            root_layout.setContentsMargins(0, 0, 0, 0)
            root_layout.setSpacing(0)

            self.session_panel = SessionPanel()
            self.session_panel.sessionSelected.connect(self._select_session)
            self.session_panel.newConnectionRequested.connect(self._new_connection)
            self.session_panel.reportRequested.connect(self.toggle_report)
            self.session_panel.profilesRequested.connect(self._manage_profiles)
            root_layout.addWidget(self.session_panel)

            content = QFrame(objectName="content")
            content_layout = QVBoxLayout(content)
            content_layout.setContentsMargins(0, 0, 0, 0)
            content_layout.setSpacing(0)
            content_layout.addWidget(self._build_topbar())
            content_layout.addWidget(self._build_session_header())
            content_layout.addWidget(self._build_command_bar())
            content_layout.addWidget(self._build_tabs())

            self.module_stack = QStackedWidget()
            self.overview_page = self._build_overview_page()
            self.terminal = TerminalWidget()
            self.terminal.disconnected.connect(lambda reason: self.log(f"Консоль: {reason}", level="warn"))
            self.file_manager = FileManagerWidget()
            self.file_manager.statusMessage.connect(self.show_status)
            self.sql_console = SqlConsoleWidget()
            self.sql_console.statusMessage.connect(self.show_status)
            self.sql_console.connectRequested.connect(self._connect_database)
            self.vnc_viewer = VncViewer()
            self.vnc_viewer.stateChanged.connect(lambda state: self.log(f"VNC: {state}"))
            self.vnc_viewer.fatal.connect(lambda message: self.log(f"VNC: {message}", level="error"))
            self.logs_page = LogsPage(self.catalog)
            self.logs_page.statusMessage.connect(self.show_status)
            self.logs_page.commandRequested.connect(self._run_catalog_command)
            self.settings_page = SettingsPage(self._settings, self._paths, self.credentials, self.catalog)
            self.settings_page.set_themes(THEMES, str(self._settings.get("theme", "dark")))
            self.settings_page.themeChanged.connect(self._apply_theme)
            self.settings_page.statusMessage.connect(self.show_status)
            self.settings_page.secretsForgetRequested.connect(self._forget_all_secrets)
            for page in (
                self.overview_page,
                self.terminal,
                self.file_manager,
                self.sql_console,
                self.vnc_viewer,
                self.logs_page,
                self.settings_page,
            ):
                self.module_stack.addWidget(page)
            content_layout.addWidget(self.module_stack, 1)

            self.setStatusBar(QStatusBar())
            self._status_label = QLabel("Готово")
            self._status_label.setObjectName("dim")
            self.statusBar().addWidget(self._status_label, 1)
            root_layout.addWidget(content, 1)
            self.setCentralWidget(root)

            self.report_dock = ReportDock(self)
            self.report_dock.refreshRequested.connect(self.collect_report)
            self.report_dock.statusMessage.connect(self.show_status)
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.report_dock)

            self.journal_dock = QDockWidget("Журнал и вывод команд", self)
            self.journal_dock.setObjectName("journalDock")
            self.journal = QPlainTextEdit()
            self.journal.setObjectName("terminalOutput")
            self.journal.setReadOnly(True)
            self.journal.setMaximumBlockCount(5000)
            journal_container = QWidget()
            journal_layout = QVBoxLayout(journal_container)
            journal_layout.setContentsMargins(6, 6, 6, 6)
            clear_button = QPushButton("Очистить", objectName="secondary")
            clear_button.clicked.connect(self.journal.clear)
            journal_layout.addWidget(self.journal, 1)
            journal_layout.addWidget(clear_button, 0, Qt.AlignmentFlag.AlignRight)
            self.journal_dock.setWidget(journal_container)
            self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.journal_dock)

            self._rebuild_command_bar()
            self._build_menu()
            self._install_shortcuts()
            self._show_module("overview")

        def _build_topbar(self) -> QWidget:
            bar = QFrame(objectName="topbar")
            bar.setFixedHeight(52)
            layout = QHBoxLayout(bar)
            layout.setContentsMargins(20, 0, 20, 0)
            layout.setSpacing(8)
            self.breadcrumb = QLabel("Сессии", objectName="muted")
            layout.addWidget(self.breadcrumb)
            layout.addStretch()

            layout.addWidget(QLabel("Тема", objectName="dim"))
            self.theme_combo = QComboBox()
            self.theme_combo.addItems([theme.label for theme in THEMES.values()])
            self.theme_combo.setCurrentText(get_theme(str(self._settings.get("theme", "dark"))).label)
            self.theme_combo.currentTextChanged.connect(self._theme_selected)
            layout.addWidget(self.theme_combo)

            self.journal_button = QPushButton("Журнал", objectName="secondary")
            self.journal_button.setCheckable(True)
            self.journal_button.toggled.connect(lambda visible: self.journal_dock.setVisible(visible))
            layout.addWidget(self.journal_button)

            self.report_button = QPushButton("Отчёт", objectName="secondary")
            self.report_button.setCheckable(True)
            self.report_button.setChecked(True)
            self.report_button.toggled.connect(lambda visible: self.report_dock.setVisible(visible))
            layout.addWidget(self.report_button)
            return bar

        def _theme_selected(self, label: str) -> None:
            for key, theme in THEMES.items():
                if theme.label == label:
                    self._apply_theme(key)
                    self.show_status(f"Тема: {theme.label}")
                    return

        def _build_session_header(self) -> QWidget:
            header = QFrame(objectName="sessionHeader")
            layout = QHBoxLayout(header)
            layout.setContentsMargins(20, 14, 20, 12)
            layout.setSpacing(12)

            self.session_icon = QLabel("▦")
            self.session_icon.setFixedSize(42, 42)
            self.session_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(self.session_icon)

            copy = QVBoxLayout()
            copy.setSpacing(3)
            self.session_title = QLabel("Касса не выбрана", objectName="pageTitle")
            self.session_meta = QLabel("Добавьте подключение, чтобы начать", objectName="muted")
            copy.addWidget(self.session_title)
            copy.addWidget(self.session_meta)
            layout.addLayout(copy)
            layout.addStretch()

            self.connection_status = QLabel("", objectName="statusOffline")
            layout.addWidget(self.connection_status)

            self.connect_button = QPushButton("Подключить", objectName="primary")
            self.connect_button.clicked.connect(self.toggle_connection)
            layout.addWidget(self.connect_button)

            self.report_now = QPushButton("▤ Сводный отчёт", objectName="secondary")
            self.report_now.clicked.connect(self.collect_report)
            layout.addWidget(self.report_now)
            return header

        def _build_command_bar(self) -> QWidget:
            frame = QFrame(objectName="sessionHeader")
            outer = QVBoxLayout(frame)
            outer.setContentsMargins(20, 10, 20, 10)
            outer.setSpacing(6)

            heading = QHBoxLayout()
            heading.addWidget(QLabel("КОМАНДЫ", objectName="eyebrow"))
            heading.addStretch()
            self.custom_command = QPushButton("＋ Своя команда", objectName="link")
            self.custom_command.clicked.connect(self._run_custom_command)
            heading.addWidget(self.custom_command)
            outer.addLayout(heading)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFixedHeight(96)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            container = QWidget()
            self.command_layout = QHBoxLayout(container)
            self.command_layout.setContentsMargins(0, 0, 0, 0)
            self.command_layout.setSpacing(14)
            scroll.setWidget(container)
            outer.addWidget(scroll)
            self._command_buttons: list[QPushButton] = []
            return frame

        def _rebuild_command_bar(self) -> None:
            while self.command_layout.count():
                item = self.command_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
            self._command_buttons.clear()

            for category, specs in self.catalog.by_category().items():
                group = QFrame()
                group_layout = QVBoxLayout(group)
                group_layout.setContentsMargins(0, 0, 0, 0)
                group_layout.setSpacing(4)
                group_layout.addWidget(QLabel(category.upper(), objectName="eyebrow"))
                row = QHBoxLayout()
                row.setSpacing(5)
                for spec in specs:
                    button = self._command_button(spec)
                    row.addWidget(button)
                    self._command_buttons.append(button)
                row.addStretch()
                group_layout.addLayout(row)
                self.command_layout.addWidget(group)
            self.command_layout.addStretch()
            self._sync_command_buttons()

        def _command_button(self, spec: CommandSpec) -> QPushButton:
            style = {Risk.DANGER: "commandDanger", Risk.CRITICAL: "commandCritical"}.get(spec.risk, "commandButton")
            button = QPushButton(f"{spec.icon}  {spec.label}")
            button.setObjectName(style)
            button.setToolTip(f"{spec.command}\n{spec.description}")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda checked=False, spec_id=spec.id: self.run_command(spec_id))
            return button

        def _sync_command_buttons(self) -> None:
            connected = self.current_session is not None and self.current_session.is_connected
            for button in self._command_buttons:
                button.setEnabled(connected)

        def _build_tabs(self) -> QWidget:
            tabs = QFrame(objectName="tabBar")
            layout = QHBoxLayout(tabs)
            layout.setContentsMargins(20, 0, 20, 0)
            layout.setSpacing(2)
            for module in self.MODULES:
                button = QPushButton(self.MODULE_LABELS[module], objectName="tab")
                button.setCheckable(True)
                button.clicked.connect(lambda checked=False, name=module: self._show_module(name))
                layout.addWidget(button)
                self._tab_buttons[module] = button
            layout.addStretch()
            return tabs

        def _show_module(self, module: str) -> None:
            index = self.MODULES.index(module)
            self.module_stack.setCurrentIndex(index)
            for name, button in self._tab_buttons.items():
                button.setChecked(name == module)

        # ------------------------------------------------------------------
        # overview page — every value comes from the cashier, nothing is mocked
        # ------------------------------------------------------------------
        def _build_overview_page(self) -> QWidget:
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setContentsMargins(20, 16, 20, 24)
            layout.setSpacing(12)

            intro = QHBoxLayout()
            copy = QVBoxLayout()
            copy.setSpacing(4)
            copy.addWidget(QLabel("СВОДКА ПО КАССЕ", objectName="eyebrowAccent"))
            self.overview_title = QLabel("Подключитесь к кассе", objectName="pageTitle")
            self.overview_subtitle = QLabel(
                "Все показатели берутся с кассы командой cash status и системными запросами.",
                objectName="muted",
            )
            self.overview_subtitle.setWordWrap(True)
            copy.addWidget(self.overview_title)
            copy.addWidget(self.overview_subtitle)
            intro.addLayout(copy)
            intro.addStretch()
            self.refresh_button = QPushButton("↻ Обновить данные", objectName="success")
            self.refresh_button.clicked.connect(self.collect_report)
            intro.addWidget(self.refresh_button, 0, Qt.AlignmentFlag.AlignBottom)
            layout.addLayout(intro)

            self.metrics_grid = QGridLayout()
            self.metrics_grid.setSpacing(10)
            for column in range(4):
                self.metrics_grid.setColumnStretch(column, 1)
            layout.addLayout(self.metrics_grid)

            lower = QGridLayout()
            lower.setSpacing(12)
            self.platform_frame, self.platform_layout = self._panel("ПЛАТФОРМА", "Что за железо и ОС")
            self.hardware_frame, self.hardware_layout = self._panel("ОБОРУДОВАНИЕ", "Подключённые устройства")
            self.detection_frame, self.detection_layout = self._panel("ОПРЕДЕЛЕНИЕ ТИПА", "Как классифицирована касса")
            lower.addWidget(self.platform_frame, 0, 0)
            lower.addWidget(self.hardware_frame, 0, 1)
            lower.addWidget(self.detection_frame, 1, 0, 1, 2)
            lower.setColumnStretch(0, 1)
            lower.setColumnStretch(1, 1)
            layout.addLayout(lower)
            layout.addStretch()
            return page

        def _panel(self, eyebrow: str, title: str) -> tuple[QFrame, QVBoxLayout]:
            frame = QFrame(objectName="panel")
            layout = QVBoxLayout(frame)
            layout.setContentsMargins(16, 14, 16, 14)
            layout.setSpacing(8)
            layout.addWidget(QLabel(eyebrow, objectName="panelEyebrow"))
            layout.addWidget(QLabel(title, objectName="sectionTitle"))
            layout.addWidget(self._divider())
            return frame, layout

        @staticmethod
        def _divider() -> QFrame:
            divider = QFrame(objectName="divider")
            divider.setFixedHeight(1)
            return divider

        def _metric(self, title: str, value: str, detail: str, style: str = "metric") -> QFrame:
            frame = QFrame(objectName=style)
            layout = QVBoxLayout(frame)
            layout.setContentsMargins(15, 13, 15, 13)
            layout.setSpacing(6)
            layout.addWidget(QLabel(title, objectName="metricLabel"))
            layout.addWidget(QLabel(value, objectName="metricValue"))
            layout.addWidget(QLabel(detail, objectName="dim"))
            return frame

        def _clear_layout(self, layout: QVBoxLayout, keep: int = 3) -> None:
            while layout.count() > keep:
                item = layout.takeAt(layout.count() - 1)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

        def _kv_row(self, layout: QVBoxLayout, key: str, value: str) -> None:
            row = QHBoxLayout()
            row.setSpacing(8)
            key_label = QLabel(key, objectName="muted")
            key_label.setMinimumWidth(150)
            value_label = QLabel(value, objectName="mono")
            value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            value_label.setWordWrap(True)
            row.addWidget(key_label)
            row.addWidget(value_label, 1)
            wrapper = QWidget()
            wrapper.setLayout(row)
            layout.addWidget(wrapper)

        def _render_overview(self, report: KassReport | None, snapshot: SessionSnapshot | None) -> None:
            while self.metrics_grid.count():
                item = self.metrics_grid.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

            if snapshot is None:
                self.overview_title.setText("Касса не выбрана")
                self.overview_subtitle.setText("Добавьте подключение слева — все данные берутся с кассы.")
                self._clear_layout(self.platform_layout)
                self._clear_layout(self.hardware_layout)
                self._clear_layout(self.detection_layout)
                return

            if report is None:
                self.overview_title.setText(snapshot.name)
                self.overview_subtitle.setText(
                    "Отчёт ещё не собран. Нажмите «Сводный отчёт», чтобы получить данные с кассы."
                )
                self.metrics_grid.addWidget(self._metric("Состояние", _state_label(snapshot.state), snapshot.host), 0, 0)
                self.metrics_grid.addWidget(self._metric("Тип", snapshot.kass_type, snapshot.location or "адрес не указан"), 0, 1)
                self._clear_layout(self.platform_layout)
                self._clear_layout(self.hardware_layout)
                self._clear_layout(self.detection_layout)
                return

            facts = report.facts
            module_state = facts.get("module_state", "неизвестно")
            self.overview_title.setText(f"{snapshot.name} · {module_state}")
            details = [part for part in (snapshot.host, facts.get("ip_address"), facts.get("os_release")) if part]
            self.overview_subtitle.setText(" · ".join(details))

            cards = (
                (
                    "Кассовый модуль",
                    module_state,
                    f"версия {facts.get('cash_version', '—')}",
                    "metricOk" if module_state == "запущен" else "metricErr",
                ),
                (
                    "Сервер SetRetail",
                    facts.get("server_status", "—"),
                    facts.get("server_ip", "адрес не определён"),
                    "metricOk" if "available" in facts.get("server_status", "").lower() else "metricWarn",
                ),
                (
                    "База данных",
                    facts.get("db_size", "—"),
                    f"службы ОФД: {facts.get('ofd_state', '—')}",
                    "metricInfo",
                ),
                (
                    "Свободно на диске",
                    facts.get("disk_free", "—"),
                    f"шлюз {facts.get('gateway', '—')}",
                    "metricInfo",
                ),
            )
            for index, (title, value, detail, style) in enumerate(cards):
                self.metrics_grid.addWidget(self._metric(title, value, detail, style), 0, index)

            self._clear_layout(self.platform_layout)
            for key, label in (
                ("os_release", "Операционная система"),
                ("kernel", "Ядро"),
                ("arch", "Архитектура"),
                ("hostname", "Имя узла"),
                ("uptime", "Время работы"),
                ("java_version", "Java"),
                ("ip_address", "IP-адреса"),
                ("gateway", "Шлюз"),
            ):
                if facts.get(key):
                    self._kv_row(self.platform_layout, label, facts[key])

            self._clear_layout(self.hardware_layout)
            rows = hardware_summary(report)
            if rows:
                for key, value in rows:
                    self._kv_row(self.hardware_layout, key, value)
            else:
                self.hardware_layout.addWidget(QLabel("Нет данных — соберите отчёт.", objectName="dim"))

            self._clear_layout(self.detection_layout)
            detection = classify(report)
            self._kv_row(self.detection_layout, "Тип кассы", detection.kass_type)
            self._kv_row(self.detection_layout, "Уверенность", f"{int(detection.confidence * 100)}%")
            explain = QLabel(detection.explain(), objectName="mono")
            explain.setWordWrap(True)
            explain.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.detection_layout.addWidget(explain)

        # ==================================================================
        # sessions
        # ==================================================================
        @property
        def current_session(self):
            return self.session_manager.active_session

        def _restore_profiles(self) -> None:
            try:
                profiles = self._profile_store.load()
            except Exception as exc:
                self._logger.warning("saved profiles could not be loaded: %s", exc)
                return
            for profile in profiles:
                try:
                    session = self.session_manager.create(profile)
                except SessionLimitError:
                    self._logger.warning("session limit reached while restoring profiles")
                    break
                session.set_sudo_resolver(self.credentials.get)

        def _refresh_sessions(self) -> None:
            self.session_panel.set_sessions(self.session_manager.snapshots(), self.session_manager.active_id)
            self._sync_command_buttons()

        def _select_session(self, session_id: str | None) -> None:
            if session_id is None:
                self._render_header(None)
                self._render_overview(None, None)
                self.report_dock.clear()
                self._sync_command_buttons()
                self.logs_page.set_available(False, "Выберите кассу, чтобы запросить её логи.")
                return
            try:
                session = self.session_manager.activate(session_id)
            except Exception as exc:
                self.show_status(str(exc))
                return
            snapshot = session.snapshot()
            self._render_header(snapshot)
            self._render_overview(self._reports.get(session_id), snapshot)
            report = self._reports.get(session_id)
            if report is not None:
                self.report_dock.set_report(report)
            else:
                self.report_dock.clear()
            self.session_panel.set_active(session_id)
            self.logs_page.set_available(
                session.is_connected,
                "" if session.is_connected else f"{snapshot.name}: подключитесь, чтобы получить логи.",
            )

        def _render_header(self, snapshot: SessionSnapshot | None) -> None:
            if snapshot is None:
                self.session_title.setText("Касса не выбрана")
                self.session_meta.setText("Добавьте подключение, чтобы начать")
                self.connection_status.setText("")
                self.connect_button.setText("Подключить")
                self.connect_button.setEnabled(False)
                self.breadcrumb.setText("Сессии")
                return
            self.session_title.setText(snapshot.name)
            details = [part for part in (snapshot.host, snapshot.kass_type, snapshot.location) if part and part != "Не определена"]
            if snapshot.version:
                details.append(f"v{snapshot.version}")
            self.session_meta.setText(" · ".join(details) or snapshot.host)
            self.breadcrumb.setText(f"Сессии  ›  {snapshot.name}")
            self.connection_status.setText(f"●  {_state_label(snapshot.state)}")
            self.connection_status.setObjectName(_state_style(snapshot.state))
            self.connection_status.style().unpolish(self.connection_status)
            self.connection_status.style().polish(self.connection_status)
            connected = snapshot.state is SessionState.CONNECTED
            self.connect_button.setText("Отключить" if connected else "Подключить")
            self.connect_button.setEnabled(True)
            if snapshot.last_error:
                self.connect_button.setToolTip(snapshot.last_error)

        def _new_connection(self) -> None:
            dialog = ConnectionDialog(parent=self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            profile = dialog.build_profile()
            self._save_profile(profile, dialog.collect_secrets())
            try:
                session = self.session_manager.create(profile)
            except SessionLimitError as exc:
                QMessageBox.warning(self, "Лимит сессий", str(exc))
                return
            session.set_sudo_resolver(self.credentials.get)
            self._refresh_sessions()
            self._select_session(session.session_id)
            self.log(f"Профиль добавлен: {profile.name}")
            self._spawn(self._connect(session.session_id))

        def _save_profile(self, profile: ConnectionProfile, secrets: dict[str, str]) -> ConnectionProfile:
            """Persist the profile, moving every typed secret into the store."""

            updated = profile
            if secrets.get("ssh"):
                reference = f"ssh:{profile.profile_id}"
                self.credentials.set(reference, secrets["ssh"])
                updated = updated.replaced(credential_ref=reference)
            if secrets.get("sudo"):
                reference = f"sudo:{profile.profile_id}"
                self.credentials.set(reference, secrets["sudo"])
                updated = updated.replaced(sudo_credential_ref=reference)
            if secrets.get("jump") and updated.jump_hosts:
                reference = f"jump:{profile.profile_id}"
                self.credentials.set(reference, secrets["jump"])
                jumps = [updated.jump_hosts[0].__class__(
                    host=updated.jump_hosts[0].host,
                    username=updated.jump_hosts[0].username,
                    port=updated.jump_hosts[0].port,
                    credential_ref=reference,
                ), *updated.jump_hosts[1:]]
                updated = updated.replaced(jump_hosts=[jump.to_dict() for jump in jumps])
            if secrets.get("vnc"):
                reference = f"vnc:{profile.profile_id}"
                self.credentials.set(reference, secrets["vnc"])
                updated = updated.replaced(vnc=updated.vnc.to_dict() | {"credential_ref": reference})
            if secrets.get("db"):
                reference = f"db:{profile.profile_id}"
                self.credentials.set(reference, secrets["db"])
                updated = updated.replaced(database=updated.database.to_dict() | {"credential_ref": reference})
            self._profile_store.upsert(updated)
            try:
                self._profile_store.save()
            except Exception as exc:
                self.log(f"Не удалось сохранить профиль: {exc}", level="error")
            return updated

        def _manage_profiles(self) -> None:
            dialog = ProfilesDialog(self._profile_store.all(), self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            action, profile = dialog.result_selection()
            if profile is None:
                return
            if action == "connect":
                self._open_existing(profile)
            elif action == "edit":
                self._edit_profile(profile)
            elif action == "delete":
                self._delete_profile(profile)

        def _open_existing(self, profile: ConnectionProfile) -> None:
            try:
                session = self.session_manager.get(profile.profile_id)
            except Exception:
                try:
                    session = self.session_manager.create(profile)
                    session.set_sudo_resolver(self.credentials.get)
                except SessionLimitError as exc:
                    QMessageBox.warning(self, "Лимит сессий", str(exc))
                    return
            self._refresh_sessions()
            self._select_session(session.session_id)
            self._spawn(self._connect(session.session_id))

        def _edit_profile(self, profile: ConnectionProfile) -> None:
            dialog = ConnectionDialog(profile, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            updated = self._save_profile(dialog.build_profile(), dialog.collect_secrets())
            try:
                session = self.session_manager.get(updated.profile_id)
            except Exception:
                return
            session.update_profile(updated)
            self._refresh_sessions()
            self._select_session(session.session_id)
            self.log(f"Профиль обновлён: {updated.name}")

        def _delete_profile(self, profile: ConnectionProfile) -> None:
            answer = QMessageBox.question(
                self,
                "Удаление профиля",
                f"Удалить профиль «{profile.name}»?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer is not QMessageBox.StandardButton.Yes:
                return
            try:
                self._profile_store.remove(profile.profile_id)
                self._profile_store.save()
            except Exception as exc:
                self.log(f"Не удалось удалить профиль: {exc}", level="error")
                return
            try:
                self._spawn(self.session_manager.remove(profile.profile_id))
            except Exception:
                pass
            self._refresh_sessions()
            self.log(f"Профиль удалён: {profile.name}")

        # ==================================================================
        # connection lifecycle
        # ==================================================================
        def toggle_connection(self) -> None:
            session = self.current_session
            if session is None:
                self._new_connection()
                return
            if session.state is SessionState.CONNECTED:
                self._spawn(self._disconnect(session.session_id))
            else:
                self._spawn(self._connect(session.session_id))

        async def _connect(self, session_id: str) -> None:
            session = self.session_manager.get(session_id)
            transport = AsyncSSHSessionTransport(self.credentials.get)
            self._transports[session_id] = transport
            self.log(f"Подключение к {session.profile.host}:{session.profile.port}…")
            self._refresh_sessions()
            try:
                await session.connect(transport)
            except SessionConnectionError as exc:
                self.log(f"Не удалось подключиться: {exc}", level="error")
                QMessageBox.warning(self, "Ошибка подключения", str(exc))
                self._refresh_sessions()
                self._render_header(session.snapshot())
                return
            self.log(f"Подключено: {transport.banner}", level="ok")
            await self._start_service_tunnels(session)
            self._refresh_sessions()
            self._render_header(session.snapshot())
            self._sync_command_buttons()
            self._sync_logs_availability(session)
            self.file_manager.attach_remote(SftpFileSystem(await transport.open_sftp()), f"/home/{session.profile.username}")
            self.show_status(f"Подключено к {session.profile.name}")

        async def _start_service_tunnels(self, session) -> None:
            """Bring up the forwards VNC and the database need."""

            transport = self._transports.get(session.session_id)
            if transport is None:
                return
            backend = AsyncSSHTunnelBackend(transport)
            wanted: list[TunnelSpec] = []
            for spec in session.profile.tunnels:
                wanted.append(spec)
            vnc_spec = session.profile.vnc.tunnel_spec
            if vnc_spec is not None:
                wanted.append(vnc_spec)
            db_spec = session.profile.database.tunnel_spec
            if db_spec is not None:
                wanted.append(db_spec)
            for spec in wanted:
                try:
                    tunnel = await self.tunnel_manager.open(spec, backend, session)
                    self.log(f"Туннель {spec.name}: 127.0.0.1:{spec.local_port} → {spec.target_host}:{spec.target_port}", level="ok")
                except Exception as exc:
                    self.log(f"Туннель {spec.name} не запущен: {exc}", level="warn")

        async def _disconnect(self, session_id: str) -> None:
            session = self.session_manager.get(session_id)
            await self.tunnel_manager.stop_for(session_id)
            for tunnel_id in session.tunnel_ids:
                session.detach_tunnel(tunnel_id)
            transport = self._transports.pop(session_id, None)
            if session.transport is None and transport is not None:
                await transport.close()
            await session.disconnect()
            self.file_manager.detach_remote()
            self._spawn(self.terminal.detach())
            self.log(f"Сессия {session.profile.name} отключена")
            self._refresh_sessions()
            self._render_header(session.snapshot())
            self._sync_command_buttons()
            self._sync_logs_availability(session)

        def _sync_logs_availability(self, session) -> None:
            """The logs tab can only fetch once there is a live connection."""

            if self.current_session is not session:
                return
            connected = bool(session.is_connected)
            self.logs_page.set_available(
                connected,
                "" if connected else f"{session.profile.name}: подключитесь, чтобы получить логи.",
            )

        # ==================================================================
        # commands
        # ==================================================================
        def run_command(self, spec_id: str) -> None:
            session = self.current_session
            if session is None:
                self.show_status("Выберите кассу")
                return
            try:
                spec = self.catalog.get(spec_id)
            except Exception as exc:
                self.show_status(str(exc))
                return
            if spec.confirm and not self._confirm_command(session, spec):
                return
            self._spawn(self._run_command(session, spec))

        def _confirm_command(self, session, spec: CommandSpec) -> bool:
            message = (
                f"Касса: {session.profile.name} ({session.profile.host})\n"
                f"Команда: {spec.command}\n\n{spec.description}"
            )
            if spec.risk is Risk.CRITICAL:
                message += "\n\nКасса полностью перезагрузится и будет недоступна несколько минут."
            answer = QMessageBox.warning(
                self,
                f"Подтвердите: {spec.label}",
                message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            return answer is QMessageBox.StandardButton.Yes

        async def _run_command(self, session, spec: CommandSpec) -> None:
            self.show_status(f"{session.profile.name}: {spec.label}…")
            self.log(f"▶ {spec.command}")
            result = await session.run(spec.command, timeout=spec.timeout)
            if result.error:
                self.log(f"✖ {result.error}", level="error")
                self.show_status(f"Ошибка: {result.error}")
                return
            body = result.output or "(пустой вывод)"
            if len(body) > 6000:
                body = body[:6000] + "\n… вывод обрезан"
            self.journal.appendPlainText(f"$ {spec.command}\n{body}")
            self.journal.appendPlainText(f"— код возврата {result.exit_code}, {result.duration_ms:.0f} мс\n")
            level = "ok" if result.ok else "warn"
            self.log(f"{spec.label}: код {result.exit_code} за {result.duration_ms:.0f} мс", level=level)
            self.show_status(f"{session.profile.name}: {spec.label} — код {result.exit_code}")
            if spec.refresh_report:
                self.collect_report()

        def _run_catalog_command(self, spec_id: str) -> None:
            """Run a catalogue command and mirror its output onto the logs page."""

            session = self.current_session
            if session is None:
                self.show_status("Выберите кассу, чтобы получить логи")
                self.logs_page.show_remote("Касса не выбрана", "")
                return
            if not session.is_connected:
                self.show_status(f"{session.profile.name}: нет подключения")
                self.logs_page.show_remote("Нет подключения", "")
                return
            try:
                spec = self.catalog.get(spec_id)
            except KeyError:
                self.log(f"Неизвестная команда: {spec_id}", level="error")
                return

            self.logs_page.set_busy(True)

            async def worker() -> None:
                try:
                    result = await session.run(spec.command, timeout=spec.timeout)
                except Exception as exc:  # transport failure must not kill the loop
                    self.log(f"✖ {spec.label}: {exc}", level="error")
                    self.logs_page.show_remote(spec.label, f"Ошибка: {exc}")
                    return
                finally:
                    self.logs_page.set_busy(False)
                if result.error:
                    self.log(f"✖ {spec.label}: {result.error}", level="error")
                    self.logs_page.show_remote(spec.label, f"Ошибка: {result.error}")
                    return
                self.journal.appendPlainText(f"$ {spec.command}\n{result.output or '(пустой вывод)'}\n")
                self.log(
                    f"{spec.label}: код {result.exit_code} за {result.duration_ms:.0f} мс",
                    level="ok" if result.ok else "warn",
                )
                self.logs_page.show_remote(
                    f"{spec.label} · {session.profile.name} · код {result.exit_code}",
                    result.output,
                )

            self._spawn(worker())

        def _forget_all_secrets(self) -> None:
            """Drop every stored password; profiles themselves are kept."""

            removed = 0
            for profile in self.session_manager.profiles():
                for reference in (
                    profile.credential_ref,
                    profile.sudo_credential_ref,
                    getattr(profile.vnc, "credential_ref", None),
                ):
                    if not reference:
                        continue
                    try:
                        self.credentials.delete(reference)
                        removed += 1
                    except Exception as exc:
                        self.log(f"Не удалось удалить секрет {reference}: {exc}", level="error")
            self.log(f"Удалено сохранённых паролей: {removed}", level="warn")
            self.show_status(f"Удалено сохранённых паролей: {removed}")

        def _run_custom_command(self) -> None:
            from PySide6.QtWidgets import QInputDialog

            session = self.current_session
            if session is None:
                self.show_status("Выберите кассу")
                return
            command, accepted = QInputDialog.getText(
                self,
                "Своя команда",
                f"Команда для {session.profile.name}:",
            )
            if not accepted or not command.strip():
                return
            spec = CommandSpec(id="custom", label="Своя команда", command=command.strip(), category="Своя команда")
            self._spawn(self._run_command(session, spec))

        # ==================================================================
        # report
        # ==================================================================
        def toggle_report(self) -> None:
            visible = not self.report_dock.isVisible()
            self.report_dock.setVisible(visible)
            self.report_button.setChecked(visible)

        def collect_report(self) -> None:
            session = self.current_session
            if session is None:
                self.show_status("Выберите кассу")
                return
            if not session.is_connected:
                self.show_status("Сначала подключитесь к кассе")
                return
            self._spawn(self._collect_report(session))

        async def _collect_report(self, session) -> None:
            options = ReportOptions(**self.report_dock.options)
            self.report_dock.set_busy(True, f"Сбор отчёта с {session.profile.host}…")
            self.report_dock.setVisible(True)
            self.report_button.setChecked(True)
            self.show_status(f"Собираю отчёт с {session.profile.name}…")
            builder = KassReportBuilder(session.profile.name, session.profile.host, options=options)
            try:
                report = await builder.collect(session.run)
            except Exception as exc:
                self.report_dock.set_busy(False, f"Ошибка сбора: {exc}")
                self.log(f"Отчёт не собран: {exc}", level="error")
                return
            self._reports[session.session_id] = report
            from ..core.report import summarise

            session.set_facts(summarise(report))
            detection = classify(report)
            if session.profile.kass_type in ("", "Не определена") and detection.kass_type != "Не определена":
                session.update_profile(session.profile.replaced(kass_type=detection.kass_type))
            self.report_dock.set_report(report)
            self._render_overview(report, session.snapshot())
            self._refresh_sessions()
            self.log(
                f"Отчёт собран: {len(report.sections)} разделов, {len(report.failed_sections)} ошибок, "
                f"{report.duration_ms / 1000:.1f} с",
                level="ok",
            )
            self.show_status(f"Отчёт по {session.profile.name} готов")

        # ==================================================================
        # terminal / vnc / database
        # ==================================================================
        def open_terminal(self) -> None:
            session = self.current_session
            if session is None or not session.is_connected:
                self.show_status("Подключитесь к кассе, чтобы открыть консоль")
                return
            self._show_module("terminal")
            self._spawn(self._open_terminal(session))

        async def _open_terminal(self, session) -> None:
            transport = self._transports.get(session.session_id)
            if transport is None:
                self.show_status("Нет транспорта для консоли")
                return
            try:
                process = await transport.open_terminal(term_size=(118, 30))
            except Exception as exc:
                self.log(f"Консоль не открыта: {exc}", level="error")
                return
            await self.terminal.attach(process, transport.banner)
            self.log(f"Консоль открыта: {transport.banner}", level="ok")

        def connect_vnc(self) -> None:
            session = self.current_session
            if session is None:
                self.show_status("Выберите кассу")
                return
            self._show_module("vnc")
            self._spawn(self._connect_vnc(session))

        async def _connect_vnc(self, session) -> None:
            settings = session.profile.vnc
            host, port = settings.host, settings.port
            if settings.via_tunnel and settings.local_port:
                host, port = "127.0.0.1", settings.local_port
            password = self.credentials.get(settings.credential_ref) if settings.credential_ref else None
            self.log(f"VNC: подключение к {host}:{port}")
            await self.vnc_viewer.connect_to(host, port, password, shared=settings.shared)

        def _connect_database(self) -> None:
            session = self.current_session
            if session is None:
                self.show_status("Выберите кассу")
                return
            self._show_module("database")
            self._spawn(self._connect_database_async(session))

        async def _connect_database_async(self, session) -> None:
            settings = session.profile.database
            host, port = settings.host, settings.port
            if settings.via_tunnel and settings.local_port:
                host, port = "127.0.0.1", settings.local_port
            password = self.credentials.get(settings.credential_ref) if settings.credential_ref else None
            existing = self._db_clients.get(session.session_id)
            if existing is not None:
                existing.dispose()
            client = DatabaseClient(settings, password)
            try:
                await client.connect_async(host=host, port=port)
                latency = await client.ping_async()
            except Exception as exc:
                self.log(f"База данных: {exc}", level="error")
                self.sql_console.set_client(None)
                self.show_status(f"Не удалось подключиться к БД: {exc}")
                return
            self._db_clients[session.session_id] = client
            self.sql_console.set_client(client, f"{settings.dialect} · {host}:{port}/{settings.database} · {latency:.0f} мс")
            self.log(f"База данных подключена: {settings.database}@{host}:{port}", level="ok")

        # ==================================================================
        # core events, menu, shortcuts
        # ==================================================================
        def _subscribe_to_core(self) -> None:
            events = self.session_manager.events
            events.subscribe("session.state_changed", lambda event: self._on_session_event(event.payload.get("snapshot")))
            events.subscribe("session.facts_changed", lambda event: self._on_session_event(event.payload.get("snapshot")))
            events.subscribe("session.profile_changed", lambda event: self._on_session_event(event.payload.get("snapshot")))
            events.subscribe("session.removed", lambda event: QTimer.singleShot(0, self._refresh_sessions))
            events.subscribe("session.created", lambda event: QTimer.singleShot(0, self._refresh_sessions))
            events.subscribe("tunnel.state_changed", self._on_tunnel_event)

        def _on_session_event(self, snapshot: SessionSnapshot | None) -> None:
            if snapshot is None:
                return
            QTimer.singleShot(0, lambda: self._apply_snapshot(snapshot))

        def _apply_snapshot(self, snapshot: SessionSnapshot) -> None:
            self.session_panel.update_session(snapshot)
            session = self.current_session
            if session is not None and session.session_id == snapshot.session_id:
                self._render_header(snapshot)
                self._sync_command_buttons()
                if not self.report_dock._report:
                    self._render_overview(self._reports.get(snapshot.session_id), snapshot)

        def _on_tunnel_event(self, event) -> None:
            snapshot = event.payload.get("snapshot")
            if snapshot is None:
                return
            if snapshot.state is TunnelState.ACTIVE:
                self.log(f"Туннель {snapshot.name} активен (127.0.0.1:{snapshot.local_port})", level="ok")
            elif snapshot.state is TunnelState.ERROR:
                self.log(f"Туннель {snapshot.name}: {snapshot.last_error}", level="error")

        def _build_menu(self) -> None:
            menu_bar = self.menuBar()
            session_menu = menu_bar.addMenu("Сессия")
            session_menu.addAction("Новое подключение…", self._new_connection, QKeySequence("Ctrl+N"))
            session_menu.addAction("Подключить / отключить", self.toggle_connection, QKeySequence("Ctrl+R"))
            session_menu.addSeparator()
            session_menu.addAction("Сохранённые профили…", self._manage_profiles)
            session_menu.addSeparator()
            session_menu.addAction("Выход", self.close, QKeySequence("Ctrl+Q"))

            view_menu = menu_bar.addMenu("Вид")
            for module in self.MODULES:
                view_menu.addAction(self.MODULE_LABELS[module], lambda name=module: self._show_module(name))
            view_menu.addSeparator()
            theme_menu = view_menu.addMenu("Тема")
            for key, theme in THEMES.items():
                theme_menu.addAction(theme.label, lambda selected=key: self._apply_theme(selected))
            view_menu.addSeparator()
            view_menu.addAction("Сводный отчёт", self.toggle_report, QKeySequence("Ctrl+T"))
            view_menu.addAction("Журнал", lambda: self.journal_dock.setVisible(not self.journal_dock.isVisible()))

            tools_menu = menu_bar.addMenu("Инструменты")
            tools_menu.addAction("Консоль SSH", self.open_terminal, QKeySequence("Ctrl+1"))
            tools_menu.addAction("Файлы", lambda: self._show_module("files"), QKeySequence("Ctrl+2"))
            tools_menu.addAction("База данных", self._connect_database, QKeySequence("Ctrl+3"))
            tools_menu.addAction("VNC", self.connect_vnc, QKeySequence("Ctrl+4"))
            tools_menu.addSeparator()
            tools_menu.addAction("Собрать отчёт", self.collect_report, QKeySequence("Ctrl+E"))
            tools_menu.addAction("Открыть журнал приложения", self._open_log_file)

        def _open_log_file(self) -> None:
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl

            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._paths.log_file)))

        def _install_shortcuts(self) -> None:
            for index in range(1, 10):
                action = QAction(self)
                action.setShortcut(QKeySequence(f"Ctrl+{index}"))
                action.triggered.connect(lambda checked=False, position=index: self._activate_by_index(position - 1))
                self.addAction(action)
            tenth = QAction(self)
            tenth.setShortcut(QKeySequence("Ctrl+0"))
            tenth.triggered.connect(lambda: self._activate_by_index(9))
            self.addAction(tenth)

        def _activate_by_index(self, index: int) -> None:
            snapshots = self.session_manager.snapshots()
            if index < len(snapshots):
                self._select_session(snapshots[index].session_id)

        # ==================================================================
        # shutdown
        # ==================================================================
        def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
            if self._closing:
                event.accept()
                return
            active = [snapshot for snapshot in self.session_manager.snapshots() if snapshot.state is SessionState.CONNECTED]
            if active:
                answer = QMessageBox.question(
                    self,
                    "Завершение работы",
                    f"Открыто активных сессий: {len(active)}. Закрыть их и выйти?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if answer is not QMessageBox.StandardButton.Yes:
                    event.ignore()
                    return
            self._closing = True
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._shutdown())
            except RuntimeError:
                asyncio.run(self._shutdown())
            event.accept()

        async def _shutdown(self) -> None:
            try:
                await self.vnc_viewer.disconnect()
            except Exception:
                pass
            for client in self._db_clients.values():
                client.dispose()
            try:
                await self.tunnel_manager.stop_all()
                await self.session_manager.close_all()
            except Exception as exc:
                self._logger.warning("shutdown warning: %s", exc)

    class ProfilesDialog(QDialog):
        """List of saved profiles with connect/edit/delete."""

        def __init__(self, profiles, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setWindowTitle("Сохранённые профили")
            self.resize(620, 420)
            self._profiles = list(profiles)
            self._action: str | None = None
            layout = QVBoxLayout(self)
            self.list_widget = QListWidget()
            self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            for profile in self._profiles:
                item = QListWidgetItem(f"{profile.name}  ·  {profile.username}@{profile.host}:{profile.port}  ·  {profile.kass_type}")
                item.setData(Qt.ItemDataRole.UserRole, profile.profile_id)
                self.list_widget.addItem(item)
            layout.addWidget(self.list_widget, 1)

            buttons = QHBoxLayout()
            for label, action, style in (
                ("Подключить", "connect", "primary"),
                ("Изменить", "edit", "secondary"),
                ("Удалить", "delete", "secondary"),
            ):
                button = QPushButton(label, objectName=style)
                button.clicked.connect(lambda checked=False, chosen=action: self._choose(chosen))
                buttons.addWidget(button)
            buttons.addStretch()
            close = QPushButton("Закрыть", objectName="secondary")
            close.clicked.connect(self.reject)
            buttons.addWidget(close)
            layout.addLayout(buttons)

        def _choose(self, action: str) -> None:
            if not self.list_widget.currentItem():
                QMessageBox.information(self, "Профили", "Выберите профиль в списке")
                return
            self._action = action
            self.accept()

        def result_selection(self) -> tuple[str | None, ConnectionProfile | None]:
            item = self.list_widget.currentItem()
            if item is None:
                return None, None
            profile_id = item.data(Qt.ItemDataRole.UserRole)
            for profile in self._profiles:
                if profile.profile_id == profile_id:
                    return self._action, profile
            return None, None

    def _escape(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _state_label(state: SessionState) -> str:
        return {
            SessionState.CONNECTED: "подключено",
            SessionState.CONNECTING: "подключение…",
            SessionState.DEGRADED: "деградация",
            SessionState.ERROR: "ошибка",
            SessionState.CLOSING: "закрытие…",
            SessionState.DISCONNECTED: "отключено",
        }.get(state, "неизвестно")

    def _state_style(state: SessionState) -> str:
        return {
            SessionState.CONNECTED: "statusOnline",
            SessionState.CONNECTING: "statusWarning",
            SessionState.DEGRADED: "statusWarning",
            SessionState.ERROR: "statusError",
        }.get(state, "statusOffline")

else:

    class MainWindow:  # type: ignore[no-redef]
        """Import-safe placeholder when PySide6 is not installed."""

        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PySide6 is required for the desktop shell; install '.[qt]'")


__all__ = ["MainWindow", "QT_AVAILABLE"]
