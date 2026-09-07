"""Smoke tests for the desktop shell.

The window is built for real (offscreen) and driven through the same code paths
a user hits: adding a profile, connecting, pressing a command button, collecting
the summary report and switching themes. When PySide6 cannot load — no Qt, or a
Linux box missing the GL libraries — the module skips rather than lying.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import socket
import tempfile
import unittest
from pathlib import Path

try:
    from PySide6.QtWidgets import QApplication, QLabel

    _APP = QApplication.instance() or QApplication([])
    _QT_ERROR: str | None = None
except Exception as exc:  # pragma: no cover - depends on the runner
    _APP = None
    _QT_ERROR = str(exc)
    QLabel = None  # type: ignore[assignment]

from cashdesk_control.core.models import ConnectionProfile

HOST = os.environ.get("CASHDESK_TEST_SSH_HOST", "127.0.0.1")
PORT = int(os.environ.get("CASHDESK_TEST_SSH_PORT", "2222"))
USER = os.environ.get("CASHDESK_TEST_SSH_USER", os.environ.get("USER", "user"))
KEY = os.environ.get("CASHDESK_TEST_SSH_KEY", "")
KNOWN_HOSTS = os.environ.get("CASHDESK_TEST_SSH_KNOWN_HOSTS", "")
REMOTE_PATH = os.environ.get("CASHDESK_TEST_SSH_PATH", "")


def _ssh_available() -> bool:
    if not KEY:
        return False
    try:
        with socket.create_connection((HOST, PORT), timeout=1.5):
            return True
    except OSError:
        return False


def _main_window_class():
    from cashdesk_control.ui.main_window import QT_AVAILABLE, MainWindow

    return MainWindow if QT_AVAILABLE else None


@unittest.skipIf(_APP is None, f"PySide6 is unavailable: {_QT_ERROR}")
class ThemeTests(unittest.TestCase):
    def test_three_themes_ship(self) -> None:
        from cashdesk_control.ui.themes import THEMES, get_theme, qss_for

        self.assertEqual(set(THEMES), {"dark", "light", "gray"})
        rendered = {key: qss_for(key) for key in THEMES}
        for key, sheet in rendered.items():
            self.assertIn("QPushButton#primary", sheet, key)
            self.assertGreater(len(sheet), 2000, key)
        # the three themes must actually differ
        self.assertEqual(len({sheet for sheet in rendered.values()}), 3)
        self.assertTrue(get_theme("light").is_dark is False)
        self.assertTrue(get_theme("dark").is_dark)
        self.assertTrue(get_theme("gray").is_dark)

    def test_unknown_theme_falls_back_to_dark(self) -> None:
        from cashdesk_control.ui.themes import get_theme

        self.assertEqual(get_theme("neon").key, "dark")
        self.assertEqual(get_theme(None).key, "dark")


@unittest.skipIf(_APP is None, f"PySide6 is unavailable: {_QT_ERROR}")
class MainWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        MainWindow = _main_window_class()
        if MainWindow is None:
            self.skipTest("PySide6 widgets are unavailable")
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self._config = Path(self._temp.name)
        for variable, value in (
            ("XDG_CONFIG_HOME", str(self._config / "config")),
            ("XDG_DATA_HOME", str(self._config / "data")),
            ("XDG_CACHE_HOME", str(self._config / "cache")),
            ("APPDATA", str(self._config / "appdata")),
            ("LOCALAPPDATA", str(self._config / "local")),
        ):
            self._patch_env(variable, value)
        self.window = MainWindow()
        self.addCleanup(self._close_window)

    def _close_window(self) -> None:
        """Close without the "active sessions?" modal blocking the runner."""

        self.window._closing = True
        self.window.close()

    def _patch_env(self, name: str, value: str) -> None:
        original = os.environ.get(name)
        os.environ[name] = value

        def restore() -> None:
            if original is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = original

        self.addCleanup(restore)

    def _pump(self, times: int = 5) -> None:
        for _ in range(times):
            _APP.processEvents()

    # -- structure -------------------------------------------------------------
    def test_window_builds_with_all_modules(self) -> None:
        self.assertEqual(self.window.module_stack.count(), len(self.window.MODULES))
        for module in self.window.MODULES:
            self.assertIn(module, self.window._tab_buttons)

    def test_no_session_means_empty_overview(self) -> None:
        self.window._select_session(None)
        self.assertEqual(self.window.session_title.text(), "Касса не выбрана")
        self.assertEqual(self.window.metrics_grid.count(), 0)

    def test_quick_command_buttons_include_restart_and_reboot(self) -> None:
        labels = {button.text() for button in self.window._command_buttons}
        self.assertTrue(any("Перезапустить кассу" in label for label in labels), labels)
        self.assertTrue(any("Полная перезагрузка" in label for label in labels), labels)
        self.assertTrue(any("Статус кассы" in label for label in labels), labels)

    def test_command_buttons_are_disabled_without_a_session(self) -> None:
        self.assertTrue(all(not button.isEnabled() for button in self.window._command_buttons))

    def test_theme_switch_changes_the_stylesheet(self) -> None:
        before = self.window.styleSheet()
        self.window._apply_theme("light")
        after = self.window.styleSheet()
        self.assertNotEqual(before, after)
        self.assertEqual(self.window._settings.get("theme"), "light")
        self.window._apply_theme("gray")
        self.assertEqual(self.window._settings.get("theme"), "gray")

    def test_report_dock_is_dockable(self) -> None:
        self.assertTrue(self.window.report_dock.isFloating() is False)
        self.assertTrue(self.window.report_dock.features() & self.window.report_dock.DockWidgetFeature.DockWidgetFloatable)

    def test_ten_session_limit_is_enforced(self) -> None:
        from cashdesk_control.core.session_manager import SessionLimitError

        for index in range(10):
            self.window.session_manager.create(
                ConnectionProfile(name=f"Касса {index}", host=f"10.0.0.{index + 1}", username="tc")
            )
        with self.assertRaises(SessionLimitError):
            self.window.session_manager.create(ConnectionProfile(name="Лишняя", host="10.0.0.99", username="tc"))

    # -- profiles ----------------------------------------------------------------
    def test_saving_a_profile_moves_the_secret_out_of_the_file(self) -> None:
        import json

        profile = ConnectionProfile(name="Магазин 1", host="10.162.1.3", username="tc")
        saved = self.window._save_profile(profile, {"ssh": "hunter2", "sudo": "sudopass", "vnc": "vncpass"})
        self.assertEqual(saved.credential_ref, f"ssh:{profile.profile_id}")
        self.assertEqual(saved.sudo_credential_ref, f"sudo:{profile.profile_id}")
        self.assertEqual(saved.vnc.credential_ref, f"vnc:{profile.profile_id}")

        raw = self.window._paths.profiles_file.read_text(encoding="utf-8")
        self.assertNotIn("hunter2", raw)
        self.assertNotIn("sudopass", raw)
        payload = json.loads(raw)
        self.assertEqual(payload["connection_profiles"][0]["host"], "10.162.1.3")

        self.assertEqual(self.window.credentials.get(saved.credential_ref), "hunter2")

    def test_header_shows_application_name_and_version(self) -> None:
        import cashdesk_control

        self.assertEqual(cashdesk_control.__version__, "0.3.0")
        self.assertEqual(
            self.window.session_panel.version_label.text(),
            f"CONTROL · v{cashdesk_control.__version__}",
        )

    def test_refresh_button_is_green_in_every_theme(self) -> None:
        from cashdesk_control.ui.themes import qss_for

        button = self.window.refresh_button
        self.assertIn("Обновить данные", button.text())
        self.assertEqual(button.objectName(), "success")
        # the QSS must actually define a green background for #success in each theme
        for key, expected in (("dark", "#3fc99a"), ("light", "#12a06c"), ("gray", "#6fd0a8")):
            sheet = qss_for(key)
            rule = sheet[sheet.index("QPushButton#success {") :]
            rule = rule[: rule.index("}")]
            self.assertIn(f"background: {expected}", rule, key)
        # and the window carries that rule once a theme is applied
        self.assertIn("QPushButton#success", self.window.styleSheet())

    def test_logs_tab_mirrors_the_journal_and_filters(self) -> None:
        logs = self.window.logs_page
        self.assertEqual(self.window.module_stack.count(), len(self.window.MODULES))
        self.assertIn("logs", self.window._tab_buttons)

        logs.clear()
        self.window.log("обычная запись")
        self.window.log("осторожно", level="warn")
        self.window.log("авария", level="error")

        self.assertEqual(len(logs._entries), 3)
        self.assertIn("обычная запись", logs.journal_view.toPlainText())

        logs.level_filter.setCurrentText("Ошибки")
        shown = logs.journal_view.toPlainText()
        self.assertIn("авария", shown)
        self.assertNotIn("обычная запись", shown)

        logs.level_filter.setCurrentText("Все")
        self.assertEqual(len(logs.journal_view.toPlainText().splitlines()), 3)
        self.assertEqual(logs.journal_count.text(), "3 записи")

    def test_logs_tab_lists_the_catalogue_log_commands(self) -> None:
        from PySide6.QtCore import Qt

        logs = self.window.logs_page
        ids = [
            logs.command_list.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(logs.command_list.count())
        ]
        self.assertIn("tail_cash_log", ids)
        self.assertIn("log_errors", ids)
        self.assertIn("journal_system", ids)
        self.assertFalse(logs.run_button.isEnabled(), "no cashier selected yet")

    def test_logs_tab_is_disabled_without_a_cashier(self) -> None:
        self.window._select_session(None)
        self._pump()
        self.assertFalse(self.window.logs_page.command_list.isEnabled())

    def test_settings_tab_reads_and_writes_the_real_store(self) -> None:
        settings_page = self.window.settings_page
        self.assertIn("settings", self.window._tab_buttons)

        settings_page.default_user.setText("tc")
        settings_page.default_port.setValue(2222)
        settings_page.command_timeout.setValue(90)
        settings_page.probe_timeout.setValue(180)
        settings_page.strict_host_keys.setChecked(False)
        settings_page.save()
        self._pump()

        self.assertEqual(self.window._settings.get("default_user"), "tc")
        self.assertEqual(self.window._settings.get("default_port"), 2222)
        self.assertEqual(self.window._settings.get("command_timeout"), 90)
        self.assertEqual(self.window._settings.get("probe_timeout"), 180)
        self.assertFalse(self.window._settings.get("strict_host_keys"))
        # written to disk, not just held in memory
        on_disk = __import__("json").loads(self.window._paths.settings_file.read_text(encoding="utf-8"))
        self.assertEqual(on_disk["default_port"], 2222)

        settings_page.default_user.setText("changed-but-not-saved")
        settings_page.reload()
        self.assertEqual(settings_page.default_user.text(), "tc")

    def test_settings_tab_shows_the_active_secret_backend(self) -> None:
        label = self.window.settings_page.backend_label.text()
        self.assertTrue(label, "backend was never reported")
        self.assertNotEqual(label, "—")

    def test_settings_tab_theme_switch_propagates(self) -> None:
        page = self.window.settings_page
        index = page.theme_combo.findData("gray")
        self.assertGreaterEqual(index, 0)
        page.theme_combo.setCurrentIndex(index)
        self._pump()
        self.assertEqual(self.window._settings.get("theme"), "gray")
        # the topbar combo follows, so the two never disagree
        self.assertEqual(self.window.theme_combo.currentText(), page.theme_combo.currentText())

    def test_profile_survives_a_restart(self) -> None:
        profile = ConnectionProfile(name="Магазин 2", host="10.162.1.4", username="tc", kass_type="SCO")
        self.window._save_profile(profile, {"ssh": "secret"})

        MainWindow = _main_window_class()
        second = MainWindow()
        self.addCleanup(second.close)
        names = [snapshot.name for snapshot in second.session_manager.snapshots()]
        self.assertIn("Магазин 2", names)
        self.assertEqual(second.session_manager.get(profile.profile_id).profile.kass_type, "SCO")


@unittest.skipIf(_APP is None, f"PySide6 is unavailable: {_QT_ERROR}")
@unittest.skipUnless(_ssh_available(), "no test SSH server configured")
class MainWindowLiveTests(unittest.IsolatedAsyncioTestCase):
    """Drive the real window against a real SSH server."""

    def setUp(self) -> None:
        MainWindow = _main_window_class()
        if MainWindow is None:
            self.skipTest("PySide6 widgets are unavailable")
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        base = Path(self._temp.name)
        for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "APPDATA", "LOCALAPPDATA"):
            original = os.environ.get(name)
            os.environ[name] = str(base / name.lower())
            self.addCleanup(self._restore, name, original)
        self.window = MainWindow()
        self.addCleanup(self._close_window)
        self.profile = ConnectionProfile(
            name="Лабораторная касса",
            host=HOST,
            port=PORT,
            username=USER,
            private_key=KEY,
            known_hosts=KNOWN_HOSTS or None,
            remote_path=REMOTE_PATH,
            profile_id="lab-kassa",
        )

    def _close_window(self) -> None:
        """Close without the "active sessions?" modal blocking the runner."""

        self.window._closing = True
        self.window.close()

    @staticmethod
    def _restore(name: str, original: str | None) -> None:
        if original is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = original

    def _pump(self, times: int = 5) -> None:
        for _ in range(times):
            _APP.processEvents()

    async def test_connect_run_command_and_collect_report(self) -> None:
        session = self.window.session_manager.create(self.profile)
        session.set_sudo_resolver(self.window.credentials.get)
        self.window._refresh_sessions()
        self.window._select_session(session.session_id)
        self._pump()

        await self.window._connect(session.session_id)
        self._pump()
        self.assertTrue(session.is_connected, session.last_error)
        self.assertTrue(all(button.isEnabled() for button in self.window._command_buttons))

        # the quick command button path, minus the modal confirmation
        await self.window._run_command(session, self.window.catalog.get("hw_platform"))
        self._pump()
        self.assertIn("ОС:", self.window.journal.toPlainText())

        await self.window._collect_report(session)
        self._pump(10)

        report = self.window._reports[session.session_id]
        self.assertEqual(self.window.report_dock.title.text(), f"{self.profile.name} · {HOST}")
        self.assertTrue(report.facts.get("arch"))
        self.assertTrue(report.facts.get("os_release"))

        # the overview is filled from the report, with no CPU/RAM cards
        self.assertEqual(self.window.metrics_grid.count(), 4)
        cards = [self.window.metrics_grid.itemAt(index).widget() for index in range(4)]
        labels = [label.text() for card in cards for label in card.findChildren(QLabel)]
        for forbidden in ("Загрузка CPU", "Память", "Оперативная"):
            self.assertNotIn(forbidden, labels, labels)
        self.assertTrue(any("Кассовый модуль" in label for label in labels), labels)

        platform_rows = self.window.platform_layout.count()
        self.assertGreater(platform_rows, 3)

        # the report dock index lists the sections, including the platform block
        index_text = "".join(
            self.window.report_dock.sections.item(row).text()
            for row in range(self.window.report_dock.sections.count())
        )
        self.assertGreater(self.window.report_dock.sections.count(), 20)
        self.assertIn("Платформа", index_text)
        self.assertNotIn("Информация о процессоре", index_text)
        self.assertNotIn("Использование памяти", index_text)

        await self.window._disconnect(session.session_id)
        self._pump()
        self.assertFalse(session.is_connected)

    async def test_command_failure_is_shown_not_raised(self) -> None:
        from cashdesk_control.core.commands import CommandSpec

        session = self.window.session_manager.create(self.profile)
        self.window._refresh_sessions()
        self.window._select_session(session.session_id)
        await self.window._connect(session.session_id)
        self._pump()

        spec = CommandSpec(id="boom", label="Падающая", command="exit 7", category="Тест")
        await self.window._run_command(session, spec)
        self._pump()
        self.assertIn("код 7", self.window.journal.toPlainText())
        await self.window._disconnect(session.session_id)

    async def test_logs_tab_pulls_real_logs_over_ssh(self) -> None:
        from PySide6.QtCore import Qt

        session = self.window.session_manager.create(self.profile)
        self.window._refresh_sessions()
        self.window._select_session(session.session_id)
        await self.window._connect(session.session_id)
        self._pump()

        logs = self.window.logs_page
        self.assertTrue(logs.command_list.isEnabled(), "selected and connected, so logs must be available")

        rows = [
            row
            for row in range(logs.command_list.count())
            if logs.command_list.item(row).data(Qt.ItemDataRole.UserRole) == "journal_system"
        ]
        self.assertTrue(rows, "journal_system missing from the log command list")
        logs.command_list.setCurrentRow(rows[0])
        self.assertTrue(logs.run_button.isEnabled())

        logs.run_button.click()
        for _ in range(40):
            await asyncio.sleep(0.1)
            self._pump()
            if "Выполняется" not in logs.remote_output.toPlainText():
                break

        text = logs.remote_output.toPlainText()
        self.assertTrue(text.startswith("# "), text[:80])
        self.assertIn("код 0", text.splitlines()[0])
        self.assertNotIn("Выполняется…", text)
        await self.window._disconnect(session.session_id)

    async def test_sftp_file_manager_attaches(self) -> None:
        session = self.window.session_manager.create(self.profile)
        self.window._refresh_sessions()
        self.window._select_session(session.session_id)
        await self.window._connect(session.session_id)
        self._pump(10)
        await self.window.file_manager.remote.open_path(f"/home/{USER}")
        self._pump(10)
        self.assertEqual(self.window.file_manager.remote.model.rowCount() > 0, True)
        self.assertEqual(self.window.file_manager.remote.badge.text(), "SFTP")
        await self.window._disconnect(session.session_id)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
