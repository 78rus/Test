"""PySide6 desktop shell for the Cashdesk Control core."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from ..core.models import ConnectionProfile, SessionSnapshot, SessionState
from ..core.session_manager import SessionLimitError, SessionManager

try:  # Keep the core importable when the optional desktop dependencies are absent.
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QAction, QKeySequence
    from PySide6.QtWidgets import (
        QApplication,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFormLayout,
        QFrame,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QMainWindow,
        QMessageBox,
        QPlainTextEdit,
        QProgressBar,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QSpinBox,
        QStackedWidget,
        QStatusBar,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )
    from .session_panel import SessionPanel
    from .styles import APP_QSS
    from .widgets.terminal import TerminalWidget
except ImportError:  # pragma: no cover - this path is expected on core-only CI.
    QT_AVAILABLE = False
    APP_QSS = ""
else:
    QT_AVAILABLE = True


if QT_AVAILABLE:

    @dataclass
    class DemoTransport:
        """A deterministic transport for the shell preview until qasync is wired."""

        opened: bool = False

        async def open(self, profile: ConnectionProfile) -> None:
            await asyncio.sleep(0)
            self.opened = True

        async def close(self) -> None:
            await asyncio.sleep(0)
            self.opened = False


    class MainWindow(QMainWindow):
        """Main window that binds the first core services to Qt widgets."""

        MODULES = ("overview", "terminal", "files", "database", "vnc", "hardware")
        MODULE_LABELS = {
            "overview": "▦  Обзор",
            "terminal": "〉_  Терминал",
            "files": "▱  Файлы",
            "database": "▤  База данных",
            "vnc": "▣  VNC",
            "hardware": "◈  Оборудование",
        }

        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setWindowTitle("Касса Control — операционный центр")
            self.setMinimumSize(1000, 680)
            self.resize(1380, 860)
            self.setStyleSheet(APP_QSS)
            self.session_manager = SessionManager(max_sessions=10)
            self._transports: dict[str, DemoTransport] = {}
            self._tab_buttons: dict[str, QPushButton] = {}
            self._seed_demo_sessions()
            self._build_ui()
            self._subscribe_to_core()
            self._refresh_sessions()
            self._select_session(self.session_manager.active_id)

        def _seed_demo_sessions(self) -> None:
            demo_profiles = (
                ConnectionProfile(
                    name="Склад · Терминал 01",
                    host="10.24.8.41",
                    username="operator",
                    profile_id="warehouse",
                    metadata={"type": "POS", "location": "Москва, Ленинский пр-т"},
                ),
                ConnectionProfile(
                    name="Кафе · Касса 02",
                    host="10.24.8.42",
                    username="operator",
                    profile_id="cafe",
                    metadata={"type": "SCO", "location": "Москва, Малая Бронная"},
                ),
                ConnectionProfile(
                    name="Магазин · Линия 03",
                    host="10.24.8.50",
                    username="operator",
                    profile_id="shop",
                    metadata={"type": "Touch", "location": "Химки, Левобережный"},
                ),
                ConnectionProfile(
                    name="Резерв · Терминал 01",
                    host="10.24.8.60",
                    username="operator",
                    profile_id="reserve",
                    metadata={"type": "Hybrid", "location": "Москва, резервный контур"},
                ),
            )
            for profile in demo_profiles:
                session = self.session_manager.create(profile)
                if profile.profile_id != "reserve":
                    transport = DemoTransport()
                    self._transports[session.session_id] = transport
                    asyncio.run(session.connect(transport))

        def _build_ui(self) -> None:
            root = QWidget(objectName="root")
            root_layout = QHBoxLayout(root)
            root_layout.setContentsMargins(0, 0, 0, 0)
            root_layout.setSpacing(0)
            self.session_panel = SessionPanel()
            self.session_panel.sessionSelected.connect(self._select_session)
            self.session_panel.newConnectionRequested.connect(self._open_new_connection)
            root_layout.addWidget(self.session_panel)

            content = QFrame(objectName="content")
            content_layout = QVBoxLayout(content)
            content_layout.setContentsMargins(0, 0, 0, 0)
            content_layout.setSpacing(0)
            content_layout.addWidget(self._build_topbar())
            content_layout.addWidget(self._build_session_header())
            content_layout.addWidget(self._build_tabs())
            self.module_stack = QStackedWidget()
            for module in self.MODULES:
                builder = getattr(self, f"_build_{module}_page")
                page = builder()
                scroll = QScrollArea()
                scroll.setWidgetResizable(True)
                scroll.setWidget(page)
                self.module_stack.addWidget(scroll)
            content_layout.addWidget(self.module_stack, 1)
            self.setStatusBar(QStatusBar())
            self.statusBar().showMessage("Готово · локальный контур")
            root_layout.addWidget(content, 1)
            self.setCentralWidget(root)

            self._install_shortcuts()

        def _build_topbar(self) -> QWidget:
            bar = QFrame()
            bar.setFixedHeight(58)
            layout = QHBoxLayout(bar)
            layout.setContentsMargins(28, 0, 28, 0)
            layout.setSpacing(8)
            self.breadcrumb = QLabel("Сессии  ›  Склад · Терминал 01", objectName="muted")
            layout.addWidget(self.breadcrumb)
            layout.addStretch()
            search = QPushButton("⌕  Поиск", objectName="secondary")
            search.setToolTip("Ctrl+K")
            search.clicked.connect(lambda: self.show_status("Быстрый поиск модулей: Ctrl+K"))
            layout.addWidget(search)
            notifications = QPushButton("◌  3", objectName="secondary")
            notifications.clicked.connect(lambda: self.show_status("3 уведомления · 1 требует внимания"))
            layout.addWidget(notifications)
            layout.addWidget(QLabel("●  Локальный контур", objectName="statusOnline"))
            return bar

        def _build_session_header(self) -> QWidget:
            header = QFrame()
            layout = QHBoxLayout(header)
            layout.setContentsMargins(28, 24, 28, 20)
            layout.setSpacing(14)
            icon = QLabel("▦")
            icon.setFixedSize(45, 45)
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon.setStyleSheet("QLabel { color: #aabbff; background: #273b81; border-radius: 11px; font-size: 22px; }")
            layout.addWidget(icon)
            copy = QVBoxLayout()
            copy.setSpacing(4)
            self.session_title = QLabel("Склад · Терминал 01", objectName="pageTitle")
            self.session_meta = QLabel("Москва, Ленинский пр-т  ·  10.24.8.41  ·  POS", objectName="muted")
            copy.addWidget(self.session_title)
            copy.addWidget(self.session_meta)
            layout.addLayout(copy)
            layout.addStretch()
            self.connection_status = QLabel("●  Подключено", objectName="statusOnline")
            layout.addWidget(self.connection_status)
            refresh = QPushButton("↻  Обновить", objectName="secondary")
            refresh.clicked.connect(self._refresh_current)
            layout.addWidget(refresh)
            terminal = QPushButton("〉_  Открыть терминал", objectName="primary")
            terminal.clicked.connect(lambda: self._show_module("terminal"))
            layout.addWidget(terminal)
            return header

        def _build_tabs(self) -> QWidget:
            tabs = QFrame()
            layout = QHBoxLayout(tabs)
            layout.setContentsMargins(28, 0, 28, 0)
            layout.setSpacing(3)
            for module in self.MODULES:
                button = QPushButton(self.MODULE_LABELS[module], objectName="tab")
                button.setCheckable(True)
                button.clicked.connect(lambda checked=False, name=module: self._show_module(name))
                layout.addWidget(button)
                self._tab_buttons[module] = button
            layout.addStretch()
            self._tab_buttons["overview"].setChecked(True)
            return tabs

        def _build_overview_page(self) -> QWidget:
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setContentsMargins(28, 24, 28, 45)
            layout.setSpacing(14)
            intro = QHBoxLayout()
            copy = QVBoxLayout()
            copy.setSpacing(5)
            copy.addWidget(QLabel("СВОДКА ПО СИСТЕМЕ", objectName="eyebrowAccent"))
            copy.addWidget(QLabel("Всё работает штатно  ✦", objectName="pageTitle"))
            copy.addWidget(QLabel("Последняя проверка завершена сегодня в 14:32. Система готова к работе.", objectName="muted"))
            intro.addLayout(copy)
            intro.addStretch()
            rescan = QPushButton("⌁  Пересканировать систему", objectName="secondary")
            rescan.clicked.connect(self._rescan)
            intro.addWidget(rescan, 0, Qt.AlignmentFlag.AlignBottom)
            layout.addLayout(intro)

            metrics = QGridLayout()
            metrics.setSpacing(10)
            metrics.addWidget(self._metric("Состояние кассы", "Онлайн", "●  Все сервисы отвечают   32 ms", "metricGreen"), 0, 0)
            metrics.addWidget(self._metric("Загрузка CPU", "42%", "↗  8.4% к прошлому часу", "metricBlue"), 0, 1)
            metrics.addWidget(self._metric("Память", "6.2 / 16 GB", "39% использовано", "metricViolet"), 0, 2)
            metrics.addWidget(self._metric("SSH-туннели", "3 активных", "●  0 ошибок за 24 часа", "metricAmber"), 0, 3)
            for column in range(4):
                metrics.setColumnStretch(column, 1)
            layout.addLayout(metrics)

            lower = QGridLayout()
            lower.setSpacing(12)
            lower.addWidget(self._services_panel(), 0, 0, 2, 1)
            lower.addWidget(self._quick_actions_panel(), 0, 1)
            lower.addWidget(self._resources_panel(), 1, 1)
            lower.addWidget(self._activity_panel(), 2, 0, 1, 2)
            lower.setColumnStretch(0, 6)
            lower.setColumnStretch(1, 4)
            layout.addLayout(lower)
            return page

        def _metric(self, title: str, value: str, detail: str, object_name: str) -> QFrame:
            frame = QFrame(objectName=object_name)
            layout = QVBoxLayout(frame)
            layout.setContentsMargins(15, 13, 15, 13)
            layout.setSpacing(7)
            layout.addWidget(QLabel(title, objectName="metricLabel"))
            layout.addWidget(QLabel(value, objectName="metricValue"))
            detail_label = QLabel(detail, objectName="dim")
            if "●" in detail:
                detail_label.setStyleSheet("QLabel { color: #7fcaa9; }")
            layout.addWidget(detail_label)
            return frame

        def _panel(self, eyebrow: str, title: str) -> tuple[QFrame, QVBoxLayout]:
            frame = QFrame(objectName="panel")
            layout = QVBoxLayout(frame)
            layout.setContentsMargins(16, 15, 16, 14)
            layout.setSpacing(9)
            layout.addWidget(QLabel(eyebrow, objectName="panelEyebrow"))
            layout.addWidget(QLabel(title, objectName="panelTitle"))
            return frame, layout

        def _services_panel(self) -> QFrame:
            frame, layout = self._panel("СЕРВИСЫ СЕССИИ", "Активные подключения")
            services = (
                ("〉_", "SSH-консоль", "OpenSSH 8.9 · порт 22", "28 ms", "terminal"),
                ("▱", "SFTP", "/opt/cashdesk · чтение и запись", "31 ms", "files"),
                ("▤", "PostgreSQL", "cashdesk · через туннель 5432", "35 ms", "database"),
                ("▣", "Удалённый экран", "VNC · localhost:5901", "44 ms", "vnc"),
            )
            for symbol, name, detail, latency, module in services:
                row = QHBoxLayout()
                row.setContentsMargins(0, 5, 0, 5)
                row.setSpacing(10)
                badge = QLabel(symbol)
                badge.setFixedSize(30, 30)
                badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
                badge.setStyleSheet("QLabel { color: #9ab0ff; background: #202b4a; border-radius: 7px; font-size: 15px; }")
                copy = QVBoxLayout()
                copy.setSpacing(1)
                copy.addWidget(QLabel(name, objectName="sessionName"))
                copy.addWidget(QLabel(detail, objectName="dim"))
                row.addWidget(badge)
                row.addLayout(copy, 1)
                row.addWidget(QLabel(latency, objectName="dim"))
                row.addWidget(QLabel("Активно", objectName="statusOnline"))
                open_button = QPushButton("↗")
                open_button.setFixedWidth(25)
                open_button.clicked.connect(lambda checked=False, selected=module: self._show_module(selected))
                row.addWidget(open_button)
                layout.addLayout(row)
            link = QPushButton("Управление подключениями  ↗")
            link.clicked.connect(lambda: self.show_status("Менеджер подключений будет подключён к ProfileStore."))
            layout.addWidget(link, 0, Qt.AlignmentFlag.AlignLeft)
            return frame

        def _quick_actions_panel(self) -> QFrame:
            frame, layout = self._panel("ИНСТРУМЕНТЫ", "Быстрые действия")
            actions = (
                ("〉_  Открыть терминал", "SSH-соединение", "terminal"),
                ("▱  Просмотреть конфиги", "12 файлов изменено", "files"),
                ("▤  Открыть базу данных", "PostgreSQL · cashdesk", "database"),
                ("⌁  Сканировать оборудование", "Последняя проверка 2 ч назад", "hardware"),
            )
            for label, detail, module in actions:
                button = QPushButton(f"{label}\n{detail}")
                button.setObjectName("secondary")
                button.setMinimumHeight(50)
                button.setStyleSheet("QPushButton { text-align: left; padding-left: 11px; }")
                button.clicked.connect(lambda checked=False, selected=module: self._show_module(selected))
                layout.addWidget(button)
            return frame

        def _resources_panel(self) -> QFrame:
            frame, layout = self._panel("МОНИТОРИНГ", "Ресурсы системы")
            for label, value, color in (("CPU", 42, "#6c8cff"), ("Память", 39, "#a58af7"), ("Диск", 64, "#f2b767")):
                row = QHBoxLayout()
                row.addWidget(QLabel(label, objectName="muted"))
                progress = QProgressBar()
                progress.setRange(0, 100)
                progress.setValue(value)
                progress.setTextVisible(False)
                progress.setFixedHeight(6)
                progress.setStyleSheet(f"QProgressBar {{ background: #29313e; border: 0; border-radius: 3px; }} QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}")
                row.addWidget(progress, 1)
                row.addWidget(QLabel(f"{value}%", objectName="dim"))
                layout.addLayout(row)
            return frame

        def _activity_panel(self) -> QFrame:
            frame, layout = self._panel("ИСТОРИЯ", "Последние события")
            events = (
                ("✓", "Проверка системы завершена", "Все 18 компонентов в норме", "14:32"),
                ("↑", "Обновлён файл конфигурации", "/opt/cashdesk/config.yml", "14:19"),
                ("▤", "Выполнен SQL-запрос", "SELECT · 24 строки · 0.12 сек", "13:47"),
            )
            for symbol, title, detail, time in events:
                row = QHBoxLayout()
                row.setContentsMargins(0, 3, 0, 3)
                marker = QLabel(symbol)
                marker.setFixedSize(23, 23)
                marker.setAlignment(Qt.AlignmentFlag.AlignCenter)
                marker.setStyleSheet("QLabel { color: #55d6a2; background: #1b342d; border-radius: 6px; font-weight: 700; }")
                copy = QVBoxLayout()
                copy.setSpacing(1)
                copy.addWidget(QLabel(title, objectName="sessionName"))
                copy.addWidget(QLabel(detail, objectName="dim"))
                row.addWidget(marker)
                row.addLayout(copy, 1)
                row.addWidget(QLabel(time, objectName="dim"))
                layout.addLayout(row)
            return frame

        def _build_terminal_page(self) -> QWidget:
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setContentsMargins(28, 24, 28, 45)
            layout.setSpacing(12)
            layout.addWidget(QLabel("SSH-СЕССИЯ", objectName="eyebrowAccent"))
            layout.addWidget(QLabel("Терминал", objectName="pageTitle"))
            layout.addWidget(QLabel("Подключение через защищённый канал с поддержкой ANSI-команд.", objectName="muted"))
            self.terminal = TerminalWidget("10.24.8.41")
            self.terminal.setMinimumHeight(480)
            self.terminal.set_command_handler(self._terminal_response)
            layout.addWidget(self.terminal, 1)
            footer = QLabel("● SSH подключён     ·     Задержка 28 ms     ·     UTF-8     ·     Ctrl+L — очистить", objectName="dim")
            layout.addWidget(footer)
            return page

        def _build_files_page(self) -> QWidget:
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setContentsMargins(28, 24, 28, 45)
            layout.setSpacing(12)
            header = QHBoxLayout()
            titles = QVBoxLayout()
            titles.addWidget(QLabel("УДАЛЁННАЯ ФАЙЛОВАЯ СИСТЕМА", objectName="eyebrowAccent"))
            titles.addWidget(QLabel("Файлы", objectName="pageTitle"))
            titles.addWidget(QLabel("SFTP подключён · /opt/cashdesk", objectName="muted"))
            header.addLayout(titles)
            header.addStretch()
            upload = QPushButton("↑  Загрузить", objectName="secondary")
            upload.clicked.connect(lambda: self.show_status("Выберите файл для загрузки в /opt/cashdesk."))
            header.addWidget(upload)
            new_file = QPushButton("＋  Новый файл", objectName="primary")
            new_file.clicked.connect(lambda: self.show_status("Создание нового файла в удалённом редакторе."))
            header.addWidget(new_file)
            layout.addLayout(header)
            split = QHBoxLayout()
            tree = QListWidget()
            tree.addItems(["▾  cashdesk", "    ▾  config", "    ▾  logs", "    ▾  scripts", "    ▸  backups"])
            tree.setFixedWidth(190)
            table = QTableWidget(5, 3)
            table.setHorizontalHeaderLabels(["Имя", "Размер", "Изменён"])
            table.setAlternatingRowColors(True)
            files = (("config.yml", "4.8 KB", "Сегодня, 14:19"), ("restart.sh", "1.2 KB", "Вчера, 18:42"), ("devices.json", "18.4 KB", "Вчера, 16:10"), ("cashdesk.log", "2.4 MB", "Сегодня, 14:31"), ("README.md", "3.1 KB", "12 авг. 2026"))
            for row, values in enumerate(files):
                for column, value in enumerate(values):
                    table.setItem(row, column, QTableWidgetItem(value))
            table.horizontalHeader().setStretchLastSection(True)
            split.addWidget(tree)
            split.addWidget(table, 1)
            layout.addLayout(split, 1)
            return page

        def _build_database_page(self) -> QWidget:
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setContentsMargins(28, 24, 28, 45)
            layout.setSpacing(12)
            header = QHBoxLayout()
            titles = QVBoxLayout()
            titles.addWidget(QLabel("POSTGRESQL · ЧЕРЕЗ SSH-ТУННЕЛЬ", objectName="eyebrowAccent"))
            titles.addWidget(QLabel("База данных", objectName="pageTitle"))
            titles.addWidget(QLabel("cashdesk · PostgreSQL 14.11 · локальный порт 55432", objectName="muted"))
            header.addLayout(titles)
            header.addStretch()
            export = QPushButton("↓  Экспорт", objectName="secondary")
            export.clicked.connect(lambda: self.show_status("Результат подготовлен к экспорту в CSV."))
            header.addWidget(export)
            layout.addLayout(header)
            editor_row = QHBoxLayout()
            self.sql_editor = QPlainTextEdit()
            self.sql_editor.setObjectName("sqlEditor")
            self.sql_editor.setPlainText("SELECT\n  order_id, status, total_amount, created_at\nFROM orders\nWHERE created_at > CURRENT_DATE - INTERVAL '1 day'\nORDER BY created_at DESC;")
            self.sql_editor.setMinimumHeight(175)
            run = QPushButton("▶  Выполнить", objectName="primary")
            run.setFixedWidth(120)
            run.clicked.connect(self._run_query)
            editor_column = QVBoxLayout()
            editor_column.addWidget(self.sql_editor)
            editor_column.addWidget(run, 0, Qt.AlignmentFlag.AlignRight)
            editor_row.addLayout(editor_column, 1)
            schema = QListWidget()
            schema.setFixedWidth(190)
            schema.addItems(["▾  public · 8 таблиц", "    ▦  orders    12.4k", "    ▦  products  428", "    ▦  cashiers  16", "    ▦  shifts    1.2k", "    ▦  terminals 4"])
            editor_row.addWidget(schema)
            layout.addLayout(editor_row)
            self.results_table = QTableWidget(4, 4)
            self.results_table.setHorizontalHeaderLabels(["order_id", "status", "total_amount", "created_at"])
            self.results_table.setAlternatingRowColors(True)
            self._fill_query_results()
            self.results_table.horizontalHeader().setStretchLastSection(True)
            layout.addWidget(self.results_table, 1)
            return page

        def _build_vnc_page(self) -> QWidget:
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setContentsMargins(28, 24, 28, 45)
            layout.setSpacing(12)
            header = QHBoxLayout()
            titles = QVBoxLayout()
            titles.addWidget(QLabel("УДАЛЁННЫЙ РАБОЧИЙ СТОЛ", objectName="eyebrowAccent"))
            titles.addWidget(QLabel("VNC", objectName="pageTitle"))
            titles.addWidget(QLabel("Экран кассы через защищённый websockify-туннель.", objectName="muted"))
            header.addLayout(titles)
            header.addStretch()
            header.addWidget(QLabel("●  44 ms", objectName="statusOnline"))
            fullscreen = QPushButton("□  На весь экран", objectName="secondary")
            fullscreen.clicked.connect(lambda: self.show_status("Полноэкранный VNC будет подключён через QWebEngineView."))
            header.addWidget(fullscreen)
            layout.addLayout(header)
            screen = QFrame(objectName="panel")
            screen_layout = QVBoxLayout(screen)
            screen_layout.setContentsMargins(0, 0, 0, 0)
            screen_label = QLabel(
                "CASHDESK                                      Терминал 01   ●       14:33\n\n"
                "     ПРОДАЖА        НОВАЯ ПРОДАЖА                         Текущий чек\n\n"
                "     [ Кофе ]       [ Сэндвич ]       [ Вода ]              3 позиции\n\n"
                "     [ Чизкейк ]     [ Капучино ]      [ Круассан ]          Итого  ₽ 760.00\n\n"
                "                                             [ Перейти к оплате ]",
                alignment=Qt.AlignmentFlag.AlignCenter,
            )
            screen_label.setMinimumHeight(430)
            screen_label.setStyleSheet("QLabel { color: #445267; background: #f3f5f7; border-radius: 8px; font-family: 'Segoe UI'; font-size: 13px; }")
            screen_layout.addWidget(screen_label)
            layout.addWidget(screen, 1)
            return page

        def _build_hardware_page(self) -> QWidget:
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setContentsMargins(28, 24, 28, 45)
            layout.setSpacing(12)
            header = QHBoxLayout()
            titles = QVBoxLayout()
            titles.addWidget(QLabel("АВТОМАТИЧЕСКИЙ СКАНЕР", objectName="eyebrowAccent"))
            titles.addWidget(QLabel("Оборудование", objectName="pageTitle"))
            titles.addWidget(QLabel("Собрано через SSH сегодня в 14:32 · 18 компонентов найдено.", objectName="muted"))
            header.addLayout(titles)
            header.addStretch()
            scan = QPushButton("⌁  Запустить сканирование", objectName="primary")
            scan.clicked.connect(self._rescan)
            header.addWidget(scan)
            layout.addLayout(header)
            detection = QFrame(objectName="metricBlue")
            detection_layout = QVBoxLayout(detection)
            detection_layout.setContentsMargins(18, 16, 18, 16)
            detection_layout.addWidget(QLabel("РЕЗУЛЬТАТ ИДЕНТИФИКАЦИИ", objectName="eyebrowAccent"))
            detection_layout.addWidget(QLabel("POS · Touch", objectName="pageTitle"))
            detection_layout.addWidget(QLabel("Уверенность определения 96%   ·   Ubuntu 22.04 LTS   ·   x86_64   ·   CashDesk 4.8.2", objectName="muted"))
            layout.addWidget(detection)
            devices = QTableWidget(6, 3)
            devices.setHorizontalHeaderLabels(["Устройство", "Интерфейс", "Состояние"])
            devices.setAlternatingRowColors(True)
            rows = (("Сканер штрихкодов", "Zebra DS2208 · USB", "Готов"), ("Чековый принтер", "АТОЛ RP-326 · USB", "Готов"), ("Весы", "Штрих-М М-ЭР · COM3", "Готов"), ("Сенсорный экран", "ViewSonic TD · HDMI", "Готов"), ("cashdesk.service", "PID 1842", "Активен"), ("tunnel-manager", "3 проброса", "Активен"))
            for row, values in enumerate(rows):
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    if column == 2:
                        item.setForeground(Qt.GlobalColor.green)
                    devices.setItem(row, column, item)
            devices.horizontalHeader().setStretchLastSection(True)
            layout.addWidget(devices, 1)
            return page

        def _subscribe_to_core(self) -> None:
            self.session_manager.events.subscribe("session.state_changed", self._on_session_event)
            self.session_manager.events.subscribe("session.created", self._on_session_event)
            self.session_manager.events.subscribe("session.removed", self._on_session_event)

        def _on_session_event(self, event) -> None:
            self._refresh_sessions()
            snapshot = event.payload.get("snapshot")
            if isinstance(snapshot, SessionSnapshot) and snapshot.session_id == self.session_manager.active_id:
                self._update_header(snapshot)

        def _refresh_sessions(self) -> None:
            self.session_panel.set_sessions(self.session_manager.snapshots(), self.session_manager.active_id)

        def _select_session(self, session_id: str | None) -> None:
            if not session_id:
                return
            session = self.session_manager.activate(session_id)
            snapshot = session.snapshot()
            self._refresh_sessions()
            self._update_header(snapshot)
            self.show_status(f"Открыта сессия «{snapshot.name}»")

        def _update_header(self, snapshot: SessionSnapshot) -> None:
            profile = self.session_manager.get(snapshot.session_id).profile
            location = profile.metadata.get("location", "Удалённый контур")
            kind = profile.metadata.get("type", "POS")
            self.session_title.setText(snapshot.name)
            self.session_meta.setText(f"{location}  ·  {snapshot.host}  ·  {kind}")
            self.breadcrumb.setText(f"Сессии  ›  {snapshot.name}")
            if snapshot.state is SessionState.CONNECTED:
                self.connection_status.setText("●  Подключено")
                self.connection_status.setObjectName("statusOnline")
            elif snapshot.state is SessionState.ERROR:
                self.connection_status.setText("●  Ошибка")
                self.connection_status.setObjectName("statusWarning")
            else:
                self.connection_status.setText("●  Не подключено")
                self.connection_status.setObjectName("statusOffline")
            self.connection_status.style().unpolish(self.connection_status)
            self.connection_status.style().polish(self.connection_status)
            if hasattr(self, "terminal"):
                self.terminal.host = snapshot.host

        def _show_module(self, module: str) -> None:
            if module not in self.MODULES:
                return
            index = self.MODULES.index(module)
            self.module_stack.setCurrentIndex(index)
            for name, button in self._tab_buttons.items():
                button.setChecked(name == module)
            if module == "terminal":
                self.terminal.input.setFocus()

        def _refresh_current(self) -> None:
            self.show_status("Состояние сессии обновлено · все сервисы отвечают")

        def _rescan(self) -> None:
            self.show_status("Сканирование оборудования запущено…")
            QTimer.singleShot(900, lambda: self.show_status("Сканирование завершено · 18 компонентов · 6 устройств готовы"))

        def _terminal_response(self, command: str) -> str:
            normalized = command.lower()
            if normalized in {"clear", "cls"}:
                self.terminal.clear()
                return ""
            if "uptime" in normalized:
                return "14:33:04 up 2 days, 6:18, 1 user, load average: 0.42, 0.38, 0.31"
            if normalized.startswith("df"):
                return "/dev/mapper/ubuntu--vg-root  200G  128G  62G  68% /"
            if "systemctl" in normalized:
                return "● cashdesk.service — active (running)"
            if normalized == "help":
                return "Доступно: systemctl status cashdesk, uptime, df -h, devices --list"
            return f"Команда выполнена на {self.session_manager.active_session.profile.host} · код 0"

        def _fill_query_results(self) -> None:
            rows = (("#104829", "paid", "₽ 2 480.00", "05.09.2026, 14:28:12"), ("#104828", "paid", "₽ 860.00", "05.09.2026, 14:25:47"), ("#104827", "pending", "₽ 1 240.00", "05.09.2026, 14:24:03"), ("#104826", "paid", "₽ 5 610.00", "05.09.2026, 14:20:58"))
            for row, values in enumerate(rows):
                for column, value in enumerate(values):
                    self.results_table.setItem(row, column, QTableWidgetItem(value))

        def _run_query(self) -> None:
            self._fill_query_results()
            self.show_status("Запрос выполнен · 24 строки · 0.12 сек")

        def _open_new_connection(self) -> None:
            dialog = QDialog(self)
            dialog.setWindowTitle("Новое подключение")
            dialog.setMinimumWidth(420)
            layout = QVBoxLayout(dialog)
            form = QFormLayout()
            name = QLineEdit(placeholderText="Например, Магазин · Касса 04")
            host = QLineEdit(placeholderText="10.24.8.51")
            user = QLineEdit("operator")
            port = QSpinBox()
            port.setRange(1, 65535)
            port.setValue(22)
            kind = QComboBox()
            kind.addItems(["POS", "SCO", "Touch", "Hybrid"])
            form.addRow("Название", name)
            form.addRow("Хост или IP", host)
            form.addRow("Пользователь", user)
            form.addRow("Порт SSH", port)
            form.addRow("Тип кассы", kind)
            layout.addLayout(form)
            layout.addWidget(QLabel("Пароли не записываются в профиль — используется системный keyring.", objectName="dim"))
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            if not name.text().strip() or not host.text().strip() or not user.text().strip():
                QMessageBox.warning(self, "Не хватает данных", "Заполните название, хост и пользователя.")
                return
            try:
                profile = ConnectionProfile(
                    name=name.text().strip(),
                    host=host.text().strip(),
                    username=user.text().strip(),
                    port=port.value(),
                    metadata={"type": kind.currentText(), "location": "Новая сессия"},
                )
                session = self.session_manager.create(profile)
                transport = DemoTransport()
                self._transports[session.session_id] = transport
                asyncio.run(session.connect(transport))
                self._select_session(session.session_id)
            except SessionLimitError as exc:
                QMessageBox.warning(self, "Лимит сессий", str(exc))
            except Exception as exc:
                QMessageBox.critical(self, "Не удалось подключиться", str(exc))

        def show_status(self, message: str) -> None:
            self.statusBar().showMessage(message, 5000)

        def _install_shortcuts(self) -> None:
            for index, module in enumerate(self.MODULES, start=1):
                action = QAction(self)
                action.setShortcut(QKeySequence(f"Ctrl+{index if index < 10 else 0}"))
                action.triggered.connect(lambda checked=False, selected=module: self._show_module(selected))
                self.addAction(action)
            clear_terminal = QAction(self)
            clear_terminal.setShortcut(QKeySequence("Ctrl+L"))
            clear_terminal.triggered.connect(lambda: self.terminal.clear())
            self.addAction(clear_terminal)

        def closeEvent(self, event) -> None:  # noqa: N802 - Qt API name.
            asyncio.run(self.session_manager.close_all())
            event.accept()

else:

    class MainWindow:  # type: ignore[no-redef]
        """Import-safe placeholder when the optional desktop stack is absent."""

        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PySide6 is required for the desktop app; install 'cashdesk-control[qt]'")


__all__ = ["APP_QSS", "MainWindow", "QT_AVAILABLE"]
