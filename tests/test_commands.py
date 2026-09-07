"""Tests for the button-driven command catalogue."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from cashdesk_control.core.commands import (
    DEFAULT_COMMANDS,
    CommandCatalog,
    CommandNotFoundError,
    CommandSpec,
    Risk,
    describe_risk,
    sudo_wrap,
)


class CommandSpecTests(unittest.TestCase):
    def test_defaults_are_valid(self) -> None:
        ids = [spec.id for spec in DEFAULT_COMMANDS]
        self.assertEqual(len(ids), len(set(ids)), "duplicate command ids")
        for spec in DEFAULT_COMMANDS:
            self.assertTrue(spec.command.strip())
            self.assertGreater(spec.timeout, 0)

    def test_restart_and_reboot_are_present_and_guarded(self) -> None:
        catalog = CommandCatalog.defaults()
        restart = catalog.get("cash_restart")
        self.assertEqual(restart.command, "cash restart")
        self.assertTrue(restart.confirm)
        self.assertIs(restart.risk, Risk.DANGER)

        reboot = catalog.get("full_reboot")
        self.assertEqual(reboot.command, "sudo reboot")
        self.assertTrue(reboot.confirm)
        self.assertTrue(reboot.needs_sudo)
        self.assertIs(reboot.risk, Risk.CRITICAL)

    def test_destructive_commands_ask_for_confirmation(self) -> None:
        for spec in DEFAULT_COMMANDS:
            if spec.is_destructive:
                self.assertTrue(spec.confirm, f"{spec.id} is destructive but has no confirmation")

    def test_empty_command_rejected(self) -> None:
        with self.assertRaises(ValueError):
            CommandSpec(id="x", label="X", command="   ")


class CatalogTests(unittest.TestCase):
    def test_grouping_by_category(self) -> None:
        grouped = CommandCatalog.defaults().by_category()
        for expected in ("Кассовый модуль", "ОФД и сервисы", "Диски и хранилище", "Сеть", "Логи", "Оборудование", "База данных"):
            self.assertIn(expected, grouped)
        # every default command lands in exactly one group
        self.assertEqual(sum(len(specs) for specs in grouped.values()), len(DEFAULT_COMMANDS))

    def test_iteration_keeps_insertion_order(self) -> None:
        catalog = CommandCatalog(
            [
                CommandSpec(id="a", label="A", command="echo a"),
                CommandSpec(id="b", label="B", command="echo b"),
            ]
        )
        self.assertEqual([spec.id for spec in catalog], ["a", "b"])

    def test_replacing_an_existing_id_keeps_position(self) -> None:
        catalog = CommandCatalog(
            [
                CommandSpec(id="a", label="A", command="echo a"),
                CommandSpec(id="b", label="B", command="echo b"),
            ]
        )
        catalog.add(CommandSpec(id="a", label="A2", command="echo a2"))
        self.assertEqual([spec.id for spec in catalog], ["a", "b"])
        self.assertEqual(catalog.get("a").label, "A2")
        self.assertEqual(len(catalog), 2)

    def test_unknown_id_raises(self) -> None:
        with self.assertRaises(CommandNotFoundError):
            CommandCatalog.defaults().get("does-not-exist")

    def test_remove(self) -> None:
        catalog = CommandCatalog.defaults()
        catalog.remove("cash_restart")
        self.assertNotIn("cash_restart", catalog)

    def test_save_and_load_round_trip(self) -> None:
        catalog = CommandCatalog.defaults()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "commands.json"
            catalog.save(path)
            loaded = CommandCatalog.load(path, base=CommandCatalog())
            self.assertEqual(len(loaded), len(catalog))
            self.assertEqual(loaded.get("cash_restart").command, "cash restart")

    def test_site_file_overrides_one_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "commands.json"
            path.write_text(
                json.dumps(
                    [{"id": "cash_restart", "label": "Перезапуск кассы", "command": "cash stop && cash start"}],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            catalog = CommandCatalog.load(path)
            self.assertEqual(catalog.get("cash_restart").command, "cash stop && cash start")
            # the rest of the built-in catalogue survives
            self.assertIn("full_reboot", catalog)

    def test_missing_file_returns_base(self) -> None:
        catalog = CommandCatalog.load("/nonexistent/commands.json")
        self.assertEqual(len(catalog), len(DEFAULT_COMMANDS))


class SudoWrapTests(unittest.TestCase):
    def test_sudo_gets_stdin_prompt_flags(self) -> None:
        spec = CommandSpec(id="reboot", label="Reboot", command="sudo reboot", needs_sudo=True)
        self.assertEqual(sudo_wrap(spec), "sudo -S -p '' reboot")

    def test_plain_command_is_untouched(self) -> None:
        spec = CommandSpec(id="status", label="Status", command="cash status")
        self.assertEqual(sudo_wrap(spec), "cash status")

    def test_only_the_first_sudo_is_rewritten(self) -> None:
        spec = CommandSpec(id="x", label="X", command="sudo sh -c 'sudo reboot'")
        self.assertEqual(sudo_wrap(spec), "sudo -S -p '' sh -c 'sudo reboot'")


class RiskDescriptionTests(unittest.TestCase):
    def test_describe_risk(self) -> None:
        spec = CommandSpec(id="reboot", label="Reboot", command="sudo reboot", risk=Risk.CRITICAL, description="Полная перезагрузка")
        text = describe_risk(spec)
        self.assertIn("Критично", text)
        self.assertIn("Полная перезагрузка", text)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
