"""Dialog for creating and editing a cashier connection profile."""

from __future__ import annotations

from typing import Any

from ..core.models import (
    KASS_TYPES,
    ConnectionProfile,
    DatabaseSettings,
    JumpHost,
    TunnelSpec,
    VncSettings,
)

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QCheckBox,
        QColorDialog,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFileDialog,
        QFormLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QSpinBox,
        QTabWidget,
        QVBoxLayout,
        QWidget,
    )
except ImportError:  # pragma: no cover
    QT_AVAILABLE = False
else:
    QT_AVAILABLE = True


if QT_AVAILABLE:

    class ConnectionDialog(QDialog):
        """Collects everything needed to reach one cashier."""

        def __init__(self, profile: ConnectionProfile | None = None, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setWindowTitle("Подключение к кассе" if profile is None else f"Профиль: {profile.name}")
            self.setMinimumWidth(560)
            self._profile = profile
            self.ssh_password: str | None = None
            self.vnc_password: str | None = None
            self.db_password: str | None = None
            self.sudo_password: str | None = None

            layout = QVBoxLayout(self)
            hint = QLabel(
                "Пароли не сохраняются в профиле — они попадают в системное хранилище ключей."
            )
            hint.setObjectName("dim")
            layout.addWidget(hint)

            tabs = QTabWidget()
            tabs.addTab(self._build_ssh_tab(), "SSH")
            tabs.addTab(self._build_cash_tab(), "Касса")
            tabs.addTab(self._build_vnc_tab(), "VNC")
            tabs.addTab(self._build_db_tab(), "База данных")
            tabs.addTab(self._build_tunnel_tab(), "Туннели")
            layout.addWidget(tabs, 1)

            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Сохранить")
            buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
            buttons.accepted.connect(self._validate_and_accept)
            buttons.rejected.connect(self.reject)
            layout.addWidget(buttons)

    # -- tabs -------------------------------------------------------------------
        def _build_ssh_tab(self) -> QWidget:
            page = QWidget()
            form = QFormLayout(page)
            form.setContentsMargins(14, 14, 14, 14)
            self.name = QLineEdit(self._profile.name if self._profile else "")
            self.name.setPlaceholderText("Магазин на Ленинском · касса 3")
            form.addRow("Название", self.name)

            host_row = QHBoxLayout()
            self.host = QLineEdit(self._profile.host if self._profile else "")
            self.host.setPlaceholderText("10.162.1.3")
            host_row.addWidget(self.host, 1)
            self.port = QSpinBox()
            self.port.setRange(1, 65535)
            self.port.setValue(self._profile.port if self._profile else 22)
            host_row.addWidget(self.port)
            form.addRow("Хост и порт", host_row)

            self.username = QLineEdit(self._profile.username if self._profile else "tc")
            form.addRow("Пользователь", self.username)

            self.password = QLineEdit()
            self.password.setEchoMode(QLineEdit.EchoMode.Password)
            self.password.setPlaceholderText("оставьте пустым, если используется ключ")
            form.addRow("Пароль SSH", self.password)

            key_row = QHBoxLayout()
            self.private_key = QLineEdit(self._profile.private_key if self._profile else "")
            self.private_key.setPlaceholderText("~/.ssh/id_ed25519")
            key_row.addWidget(self.private_key, 1)
            browse = QPushButton("Обзор…", objectName="secondary")
            browse.clicked.connect(self._pick_key)
            key_row.addWidget(browse)
            form.addRow("Приватный ключ", key_row)

            self.sudo_password = QLineEdit()
            self.sudo_password.setEchoMode(QLineEdit.EchoMode.Password)
            self.sudo_password.setPlaceholderText("для sudo reboot; пусто — использовать пароль SSH")
            form.addRow("Пароль sudo", self.sudo_password)

            self.remote_path = QLineEdit(self._profile.remote_path if self._profile else "/home/tc/bin")
            self.remote_path.setPlaceholderText("каталоги, где лежит cash")
            form.addRow("PATH кассы", self.remote_path)

            self.jump_host = QLineEdit()
            jump_value = self._profile.jump_hosts[0] if self._profile and self._profile.jump_hosts else None
            if jump_value:
                self.jump_host.setText(f"{jump_value.username}@{jump_value.host}:{jump_value.port}")
            self.jump_host.setPlaceholderText("user@jump-host:22 — если касса недоступна напрямую")
            form.addRow("Jump host", self.jump_host)

            self.jump_password = QLineEdit()
            self.jump_password.setEchoMode(QLineEdit.EchoMode.Password)
            form.addRow("Пароль jump", self.jump_password)
            return page

        def _build_cash_tab(self) -> QWidget:
            page = QWidget()
            form = QFormLayout(page)
            form.setContentsMargins(14, 14, 14, 14)
            self.kass_type = QComboBox()
            self.kass_type.addItems(list(KASS_TYPES))
            if self._profile and self._profile.kass_type in KASS_TYPES:
                self.kass_type.setCurrentText(self._profile.kass_type)
            form.addRow("Тип кассы", self.kass_type)

            self.location = QLineEdit(self._profile.location if self._profile else "")
            self.location.setPlaceholderText("Москва, Ленинский пр-т, 12")
            form.addRow("Адрес", self.location)

            self.color = QComboBox()
            self.color.addItems(["blue", "green", "amber", "violet", "rose", "slate"])
            if self._profile and self._profile.color:
                self.color.setCurrentText(self._profile.color)
            form.addRow("Цвет сессии", self.color)
            return page

        def _build_vnc_tab(self) -> QWidget:
            page = QWidget()
            form = QFormLayout(page)
            form.setContentsMargins(14, 14, 14, 14)
            vnc = self._profile.vnc if self._profile else VncSettings()

            self.vnc_host = QLineEdit(vnc.host)
            self.vnc_host.setPlaceholderText("127.0.0.1 — VNC на самой кассе")
            form.addRow("Хост VNC", self.vnc_host)

            self.vnc_port = QSpinBox()
            self.vnc_port.setRange(1, 65535)
            self.vnc_port.setValue(vnc.port)
            form.addRow("Порт VNC", self.vnc_port)

            self.vnc_local_port = QSpinBox()
            self.vnc_local_port.setRange(0, 65535)
            self.vnc_local_port.setValue(vnc.local_port or 0)
            self.vnc_local_port.setSpecialValueText("авто")
            form.addRow("Локальный порт", self.vnc_local_port)

            self.vnc_via_tunnel = QCheckBox("Пробрасывать порт VNC через SSH-туннель")
            self.vnc_via_tunnel.setChecked(vnc.via_tunnel)
            form.addRow("", self.vnc_via_tunnel)

            self.vnc_password = QLineEdit()
            self.vnc_password.setEchoMode(QLineEdit.EchoMode.Password)
            form.addRow("Пароль VNC", self.vnc_password)
            return page

        def _build_db_tab(self) -> QWidget:
            page = QWidget()
            form = QFormLayout(page)
            form.setContentsMargins(14, 14, 14, 14)
            db = self._profile.database if self._profile else DatabaseSettings()

            self.db_dialect = QComboBox()
            self.db_dialect.addItems(["postgresql", "sqlite", "mysql", "mssql", "oracle"])
            self.db_dialect.setCurrentText(db.dialect)
            form.addRow("СУБД", self.db_dialect)

            self.db_host = QLineEdit(db.host)
            form.addRow("Хост", self.db_host)

            self.db_port = QSpinBox()
            self.db_port.setRange(1, 65535)
            self.db_port.setValue(db.port)
            form.addRow("Порт", self.db_port)

            self.db_name = QLineEdit(db.database)
            form.addRow("База", self.db_name)

            self.db_user = QLineEdit(db.username)
            form.addRow("Пользователь", self.db_user)

            self.db_schema = QLineEdit(db.schema)
            form.addRow("Схема", self.db_schema)

            self.db_local_port = QSpinBox()
            self.db_local_port.setRange(0, 65535)
            self.db_local_port.setValue(db.local_port or 0)
            self.db_local_port.setSpecialValueText("авто")
            form.addRow("Локальный порт", self.db_local_port)

            self.db_via_tunnel = QCheckBox("Подключаться через SSH-туннель")
            self.db_via_tunnel.setChecked(db.via_tunnel)
            form.addRow("", self.db_via_tunnel)

            self.db_password = QLineEdit()
            self.db_password.setEchoMode(QLineEdit.EchoMode.Password)
            form.addRow("Пароль БД", self.db_password)
            return page

        def _build_tunnel_tab(self) -> QWidget:
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setContentsMargins(14, 14, 14, 14)
            explanation = QLabel(
                "Дополнительные пробросы портов. Туннели для VNC и базы данных "
                "создаются автоматически из их настроек."
            )
            explanation.setObjectName("dim")
            explanation.setWordWrap(True)
            layout.addWidget(explanation)
            self.tunnels_text = QLineEdit()
            existing = ", ".join(
                f"{spec.name}={spec.local_port}->{spec.target_host}:{spec.target_port}"
                for spec in (self._profile.tunnels if self._profile else ())
            )
            self.tunnels_text.setText(existing)
            self.tunnels_text.setPlaceholderText("printer=9100->127.0.0.1:9100, weigher=4001->10.0.0.5:4001")
            layout.addWidget(self.tunnels_text)
            layout.addStretch()
            return page

    # -- actions ------------------------------------------------------------------
        def _pick_key(self) -> None:
            path, _ = QFileDialog.getOpenFileName(self, "Приватный ключ SSH")
            if path:
                self.private_key.setText(path)

        def _validate_and_accept(self) -> None:
            try:
                self.build_profile()
            except ValueError as exc:
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.warning(self, "Проверьте данные", str(exc))
                return
            self.accept()

        @staticmethod
        def _parse_jump(value: str) -> JumpHost | None:
            value = value.strip()
            if not value:
                return None
            user, _, rest = value.partition("@")
            if not rest:
                raise ValueError("jump host должен быть в виде user@host:port")
            host, _, port_text = rest.partition(":")
            port = int(port_text) if port_text else 22
            return JumpHost(host=host, username=user, port=port)

        @staticmethod
        def _parse_tunnels(value: str) -> tuple[TunnelSpec, ...]:
            specs: list[TunnelSpec] = []
            for chunk in value.split(","):
                chunk = chunk.strip()
                if not chunk:
                    continue
                name, _, target = chunk.partition("=")
                local_text, _, remote = target.partition("->")
                remote_host, _, remote_port = remote.rpartition(":")
                specs.append(
                    TunnelSpec(
                        name=name.strip(),
                        local_port=int(local_text.strip()),
                        target_host=remote_host.strip(),
                        target_port=int(remote_port.strip()),
                    )
                )
            return tuple(specs)

        def build_profile(self) -> ConnectionProfile:
            """Assemble the profile; raises ``ValueError`` on bad input."""

            name = self.name.text().strip()
            host = self.host.text().strip()
            if not name:
                raise ValueError("Укажите название подключения")
            if not host:
                raise ValueError("Укажите адрес кассы")

            jump = self._parse_jump(self.jump_host.text())
            profile_id = self._profile.profile_id if self._profile else None

            data: dict[str, Any] = {
                "name": name,
                "host": host,
                "port": self.port.value(),
                "username": self.username.text().strip() or "tc",
                "private_key": self.private_key.text().strip() or None,
                "jump_hosts": [jump.to_dict()] if jump else [],
                "tunnels": [spec.to_dict() for spec in self._parse_tunnels(self.tunnels_text.text())],
                "kass_type": self.kass_type.currentText(),
                "location": self.location.text().strip(),
                "color": self.color.currentText(),
                "remote_path": self.remote_path.text().strip(),
                "database": {
                    "dialect": self.db_dialect.currentText(),
                    "host": self.db_host.text().strip() or "127.0.0.1",
                    "port": self.db_port.value(),
                    "database": self.db_name.text().strip() or "cash",
                    "username": self.db_user.text().strip() or "postgres",
                    "schema": self.db_schema.text().strip() or "public",
                    "via_tunnel": self.db_via_tunnel.isChecked(),
                    "local_port": self.db_local_port.value() or None,
                },
                "vnc": {
                    "host": self.vnc_host.text().strip() or "127.0.0.1",
                    "port": self.vnc_port.value(),
                    "via_tunnel": self.vnc_via_tunnel.isChecked(),
                    "local_port": self.vnc_local_port.value() or None,
                },
            }
            if profile_id:
                data["profile_id"] = profile_id
                if self._profile:
                    data["credential_ref"] = self._profile.credential_ref
                    data["sudo_credential_ref"] = self._profile.sudo_credential_ref
                    data["known_hosts"] = self._profile.known_hosts
                    data["database"]["credential_ref"] = self._profile.database.credential_ref
                    data["vnc"]["credential_ref"] = self._profile.vnc.credential_ref
            return ConnectionProfile.from_dict(data)

        def collect_secrets(self) -> dict[str, str]:
            """Passwords typed by the user, keyed by their intended purpose."""

            secrets = {
                "ssh": self.password.text(),
                "sudo": self.sudo_password.text(),
                "vnc": self.vnc_password.text(),
                "db": self.db_password.text(),
                "jump": self.jump_password.text(),
            }
            return {key: value for key, value in secrets.items() if value}

else:

    class ConnectionDialog:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PySide6 is required for the connection dialog")
