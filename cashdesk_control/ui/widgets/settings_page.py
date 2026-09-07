"""Settings module.

Everything here reads from and writes to the real stores: ``SettingsStore`` for
non-secret preferences, the credential store for secrets, and ``AppPaths`` for
the on-disk locations. Nothing is decorative — each field changes behaviour.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ...core.commands import CommandCatalog
from ...core.paths import AppPaths
from ...core.settings import SettingsStore

try:
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QFileDialog,
        QFormLayout,
        QFrame,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QScrollArea,
        QSpinBox,
        QVBoxLayout,
        QWidget,
    )

    QT_AVAILABLE = True
except ImportError:  # pragma: no cover - core-only install
    QT_AVAILABLE = False


if QT_AVAILABLE:

    class SettingsPage(QWidget):
        """Application preferences."""

        themeChanged = Signal(str)
        statusMessage = Signal(str)
        secretsForgetRequested = Signal()

        def __init__(
            self,
            settings: SettingsStore,
            paths: AppPaths,
            credentials: Any,
            catalog: CommandCatalog | None = None,
            parent: QWidget | None = None,
        ) -> None:
            super().__init__(parent)
            self._settings = settings
            self._paths = paths
            self._credentials = credentials
            self._catalog = catalog
            self._logger = logging.getLogger("cashdesk_control.settings")
            self._build_ui()
            self.reload()

        # -- ui -----------------------------------------------------------
        def _build_ui(self) -> None:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            body = QWidget()
            body.setObjectName("settingsBody")
            layout = QVBoxLayout(body)
            layout.setContentsMargins(18, 16, 18, 20)
            layout.setSpacing(14)

            # -- appearance
            appearance, appearance_form = self._card("ВНЕШНИЙ ВИД", "Тема и плотность интерфейса")
            self.theme_combo = QComboBox()
            self.theme_combo.currentTextChanged.connect(self._theme_selected)
            appearance_form.addRow("Тема", self.theme_combo)
            layout.addWidget(appearance)

            # -- connection defaults
            connection, connection_form = self._card("ПОДКЛЮЧЕНИЕ ПО УМОЛЧАНИЮ", "Значения для новых касс")
            self.default_user = QLineEdit()
            self.default_user.setPlaceholderText("tc")
            connection_form.addRow("Пользователь", self.default_user)

            self.default_port = QSpinBox()
            self.default_port.setRange(1, 65535)
            self.default_port.setValue(22)
            connection_form.addRow("SSH-порт", self.default_port)

            self.command_timeout = QSpinBox()
            self.command_timeout.setRange(5, 600)
            self.command_timeout.setSuffix(" с")
            connection_form.addRow("Таймаут команды", self.command_timeout)

            self.known_hosts = QLineEdit()
            self.known_hosts.setPlaceholderText("~/.ssh/known_hosts")
            browse_hosts = QPushButton("…", objectName="secondary")
            browse_hosts.setFixedWidth(32)
            browse_hosts.clicked.connect(lambda: self._browse(self.known_hosts, "known_hosts"))
            hosts_row = QHBoxLayout()
            hosts_row.setSpacing(6)
            hosts_row.addWidget(self.known_hosts, 1)
            hosts_row.addWidget(browse_hosts)
            connection_form.addRow("known_hosts", hosts_row)
            layout.addWidget(connection)

            # -- report
            report, report_form = self._card("СВОДНЫЙ ОТЧЁТ", "Как собирается диагностика")
            self.probe_timeout = QSpinBox()
            self.probe_timeout.setRange(5, 900)
            self.probe_timeout.setSuffix(" с")
            report_form.addRow("Таймаут пробы", self.probe_timeout)
            self.strict_host_keys = QCheckBox("Требовать проверку ключа хоста")
            report_form.addRow("", self.strict_host_keys)
            layout.addWidget(report)

            # -- security
            security, security_form = self._card("ПАРОЛИ", "Где хранятся секреты")
            self.backend_label = QLabel("—", objectName="muted")
            security_form.addRow("Хранилище", self.backend_label)
            self.vault_label = QLabel("—", objectName="muted")
            self.vault_label.setWordWrap(True)
            self.vault_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            security_form.addRow("Файл-хранилище", self.vault_label)
            note = QLabel(
                "Пароли не сохраняются в файлах профилей. Приоритет отдаётся системному "
                "хранилищу ключей; если оно недоступно, используется файл, зашифрованный "
                "Fernet, с ключом 0600 рядом.",
                objectName="dim",
            )
            note.setWordWrap(True)
            security_form.addRow("", note)
            forget = QPushButton("Забыть все сохранённые пароли", objectName="secondary")
            forget.clicked.connect(self._forget)
            security_form.addRow("", forget)
            layout.addWidget(security)

            # -- paths
            paths_card, paths_form = self._card("ФАЙЛЫ", "Каталоги приложения")
            for label, value in (
                ("Настройки", self._paths.settings_file),
                ("Профили", self._paths.profiles_file),
                ("Журнал", self._paths.log_file),
                ("Кэш", self._paths.cache_dir),
            ):
                field = QLabel(str(value), objectName="muted")
                field.setWordWrap(True)
                field.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                paths_form.addRow(label, field)
            layout.addWidget(paths_card)

            # -- commands
            commands_card, commands_form = self._card("КОМАНДЫ", "Каталог действий")
            self.commands_path = QLabel(str(self._paths.config_dir / "commands.json"), objectName="muted")
            self.commands_path.setWordWrap(True)
            commands_form.addRow("commands.json", self.commands_path)
            self.commands_hint = QLabel("—", objectName="dim")
            commands_form.addRow("", self.commands_hint)
            layout.addWidget(commands_card)

            # -- actions
            actions = QHBoxLayout()
            save_button = QPushButton("Сохранить настройки", objectName="primary")
            save_button.clicked.connect(self.save)
            reload_button = QPushButton("Отменить изменения", objectName="secondary")
            reload_button.clicked.connect(self.reload)
            actions.addWidget(save_button)
            actions.addWidget(reload_button)
            actions.addStretch()
            layout.addLayout(actions)
            layout.addStretch()

            scroll.setWidget(body)
            outer = QVBoxLayout(self)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.addWidget(scroll)

        def _card(self, eyebrow: str, title: str) -> tuple[QFrame, QFormLayout]:
            frame = QFrame(objectName="panel")
            outer = QVBoxLayout(frame)
            outer.setContentsMargins(16, 14, 16, 14)
            outer.setSpacing(6)
            outer.addWidget(QLabel(eyebrow, objectName="panelEyebrow"))
            outer.addWidget(QLabel(title, objectName="sectionTitle"))
            form = QFormLayout()
            form.setContentsMargins(0, 6, 0, 0)
            form.setHorizontalSpacing(16)
            form.setVerticalSpacing(10)
            outer.addLayout(form)
            return frame, form

        # -- data -----------------------------------------------------------
        def set_themes(self, themes: dict[str, Any], current: str) -> None:
            self.theme_combo.blockSignals(True)
            self.theme_combo.clear()
            for key, theme in themes.items():
                self.theme_combo.addItem(getattr(theme, "label", str(key)), userData=key)
            index = self.theme_combo.findData(current)
            self.theme_combo.setCurrentIndex(max(index, 0))
            self.theme_combo.blockSignals(False)

        def set_catalog(self, catalog: CommandCatalog) -> None:
            specs = catalog.to_list()
            source = "пользовательского commands.json" if self._user_catalog_exists() else "встроенного каталога"
            self.commands_hint.setText(f"{len(specs)} команд из {source}")

        def _user_catalog_exists(self) -> bool:
            return (self._paths.config_dir / "commands.json").exists()

        def reload(self) -> None:
            self.default_user.setText(str(self._settings.get("default_user", "")))
            self.default_port.setValue(int(self._settings.get("default_port", 22)))
            self.command_timeout.setValue(int(self._settings.get("command_timeout", 60)))
            self.known_hosts.setText(str(self._settings.get("known_hosts", "")))
            self.probe_timeout.setValue(int(self._settings.get("probe_timeout", 120)))
            self.strict_host_keys.setChecked(bool(self._settings.get("strict_host_keys", True)))

            backend = getattr(self._credentials, "backend", None)
            self.backend_label.setText(str(backend()) if callable(backend) else type(self._credentials).__name__)
            vault = getattr(self._credentials, "fallback", None)
            vault_path = getattr(vault, "path", None)
            self.vault_label.setText(str(vault_path) if vault_path is not None else "не используется")
            if self._catalog is not None:
                self.set_catalog(self._catalog)

        def save(self) -> None:
            self._settings.update(
                {
                    "default_user": self.default_user.text().strip(),
                    "default_port": int(self.default_port.value()),
                    "command_timeout": int(self.command_timeout.value()),
                    "known_hosts": self.known_hosts.text().strip(),
                    "probe_timeout": int(self.probe_timeout.value()),
                    "strict_host_keys": bool(self.strict_host_keys.isChecked()),
                }
            )
            try:
                self._settings.save()
            except Exception as exc:
                self._logger.error("settings could not be saved: %s", exc)
                self.statusMessage.emit(f"Не удалось сохранить настройки: {exc}")
                return
            self.statusMessage.emit("Настройки сохранены")

        def _theme_selected(self, label: str) -> None:
            key = self.theme_combo.currentData()
            if key:
                self.themeChanged.emit(str(key))

        def _browse(self, target: QLineEdit, title: str) -> None:
            path, _ = QFileDialog.getOpenFileName(self, title, target.text() or str(Path.home()))
            if path:
                target.setText(path)

        def _forget(self) -> None:
            from PySide6.QtWidgets import QMessageBox

            answer = QMessageBox.question(
                self,
                "Забыть пароли",
                "Удалить все сохранённые пароли и ключи? Профили подключений останутся.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                self.secretsForgetRequested.emit()


__all__ = ["SettingsPage", "QT_AVAILABLE"]
