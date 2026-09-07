"""Tests for the cashier summary report: probes, parsing and rendering."""

from __future__ import annotations

import unittest

from cashdesk_control.core.models import CommandResult
from cashdesk_control.core.report import (
    STATUS_EMPTY,
    STATUS_ERROR,
    STATUS_OK,
    STATUS_SKIPPED,
    KassReportBuilder,
    ReportOptions,
    default_probes,
    load_custom_probes,
    parse_cash_status,
    summarise,
)

CASH_STATUS = """*** Set Retail Cash status ***

POS Loaded       : YES

OS Release       : Ubuntu 22.04.4 LTS
IP address       : 10.162.1.3 172.17.0.1
Gateway          : 10.162.1.253
DB Size          : 369M
TCE Path         : /opt/tce
Disk free        : 23.3G

Server IP        : 10.5.1.129
Server status    : Not available
"""


class FakeRunner:
    """Stands in for a session transport: replies from a fixed command table."""

    def __init__(self, responses: dict[str, CommandResult] | None = None, default: str = "") -> None:
        self.responses = responses or {}
        self.default = default
        self.calls: list[str] = []

    async def __call__(self, command: str, *, timeout: float = 60.0) -> CommandResult:
        self.calls.append(command)
        if command in self.responses:
            return self.responses[command]
        for needle, result in self.responses.items():
            if needle in command:
                return result
        return CommandResult(command=command, stdout=self.default)


class CashStatusParsingTests(unittest.TestCase):
    def test_extracts_known_keys(self) -> None:
        facts = parse_cash_status(CASH_STATUS)
        self.assertEqual(facts["os_release"], "Ubuntu 22.04.4 LTS")
        self.assertEqual(facts["db_size"], "369M")
        self.assertEqual(facts["disk_free"], "23.3G")
        self.assertEqual(facts["server_ip"], "10.5.1.129")
        self.assertEqual(facts["server_status"], "Not available")
        self.assertEqual(facts["module_state"], "запущен")

    def test_ignores_unknown_lines(self) -> None:
        self.assertEqual(parse_cash_status("*** заголовок ***\n\n"), {})

    def test_not_loaded_module(self) -> None:
        facts = parse_cash_status("POS Loaded       : NO\n")
        self.assertEqual(facts["module_state"], "не запущен")


class ReportBuilderTests(unittest.IsolatedAsyncioTestCase):
    async def test_collects_sections_and_facts(self) -> None:
        runner = FakeRunner(
            {
                "cash status": CommandResult(command="cash status", stdout=CASH_STATUS),
                "cash version": CommandResult(command="cash version", stdout="10.4.27.19\n"),
                "PRETTY_NAME": CommandResult(
                    command="platform",
                    stdout="ОС: Ubuntu 22.04.4 LTS\nЯдро: 6.8.0-52-generic\nАрхитектура: x86_64\n"
                    "Аптайм: up 5 hours\nИмя узла: kassa-03\n",
                ),
            }
        )
        builder = KassReportBuilder("Касса 03", "10.162.1.3")
        report = await builder.collect(runner)

        self.assertEqual(report.session_name, "Касса 03")
        self.assertEqual(report.facts["cash_version"], "10.4.27.19")
        self.assertEqual(report.facts["os_release"], "Ubuntu 22.04.4 LTS")
        self.assertEqual(report.facts["kernel"], "6.8.0-52-generic")
        self.assertEqual(report.facts["arch"], "x86_64")
        self.assertEqual(report.facts["module_state"], "запущен")
        self.assertEqual(report.facts["db_size"], "369M")

        section = report.section("2.1")
        self.assertIsNotNone(section)
        self.assertEqual(section.status, STATUS_OK)
        self.assertIn("POS Loaded", section.body)

    async def test_failed_probe_does_not_abort_the_report(self) -> None:
        runner = FakeRunner(
            {
                "lsusb": CommandResult(command="lsusb", stderr="lsusb: command not found", exit_code=127),
                "cash status": CommandResult(command="cash status", stdout=CASH_STATUS),
            }
        )
        report = await KassReportBuilder("Касса", "10.0.0.1").collect(runner)
        usb = report.section("6.11")
        self.assertEqual(usb.status, STATUS_ERROR)
        self.assertIn("127", usb.error)
        self.assertTrue(report.errors)
        # the rest of the report still collected
        self.assertEqual(report.section("2.1").status, STATUS_OK)

    async def test_empty_probe_is_marked_empty(self) -> None:
        report = await KassReportBuilder("Касса", "10.0.0.1").collect(FakeRunner())
        self.assertEqual(report.section("4.8").status, STATUS_EMPTY)
        text = report.render_text()
        self.assertIn("нет данных", text)

    async def test_cpu_and_memory_dumps_are_not_collected(self) -> None:
        """The report must not fetch /proc/cpuinfo, /proc/meminfo, free or top."""

        runner = FakeRunner()
        await KassReportBuilder("Касса", "10.0.0.1").collect(runner)
        joined = "\n".join(runner.calls)
        for forbidden in ("/proc/cpuinfo", "/proc/meminfo", "free -m", "top -b", " top "):
            self.assertNotIn(forbidden, joined, f"report still collects {forbidden!r}")

    async def test_optional_probes_are_skipped_by_default(self) -> None:
        report = await KassReportBuilder("Касса", "10.0.0.1").collect(FakeRunner())
        self.assertEqual(report.section("7").status, STATUS_SKIPPED)
        enabled = await KassReportBuilder(
            "Касса", "10.0.0.1", options=ReportOptions(include_jar_versions=True)
        ).collect(FakeRunner())
        self.assertNotEqual(enabled.section("7").status, STATUS_SKIPPED)

    async def test_reboot_history_can_be_switched_off(self) -> None:
        report = await KassReportBuilder(
            "Касса", "10.0.0.1", options=ReportOptions(include_reboot_history=False)
        ).collect(FakeRunner())
        self.assertEqual(report.section("6.2").status, STATUS_SKIPPED)

    async def test_heading_levels(self) -> None:
        report = await KassReportBuilder("Касса", "10.0.0.1").collect(FakeRunner())
        self.assertEqual(report.section("1").heading, "[1. Информация по времени]")
        self.assertTrue(report.section("2.1").heading.startswith("[[2.1."))
        self.assertTrue(report.section("6.1.1").heading.startswith("[[[6.1.1."))

    async def test_render_text_contains_header_facts(self) -> None:
        runner = FakeRunner({"cash status": CommandResult(command="cash status", stdout=CASH_STATUS)})
        report = await KassReportBuilder("Касса 03", "10.162.1.3").collect(runner)
        text = report.render_text()
        self.assertIn("Касса: Касса 03 (10.162.1.3)", text)
        self.assertIn("ОС: Ubuntu 22.04.4 LTS", text)
        self.assertIn("Кассовый модуль: запущен", text)

    async def test_markdown_export(self) -> None:
        report = await KassReportBuilder("Касса", "10.0.0.1").collect(FakeRunner())
        markdown = report.render_markdown()
        self.assertIn("# Отчёт по кассе Касса", markdown)
        self.assertIn("## 1. Информация по времени", markdown)

    async def test_summarise_only_keeps_known_facts(self) -> None:
        runner = FakeRunner({"cash status": CommandResult(command="cash status", stdout=CASH_STATUS)})
        report = await KassReportBuilder("Касса", "10.0.0.1").collect(runner)
        summary = summarise(report)
        self.assertEqual(summary["db_size"], "369M")
        self.assertNotIn("hostname", summary)

    async def test_to_dict_is_serialisable(self) -> None:
        import json

        report = await KassReportBuilder("Касса", "10.0.0.1").collect(FakeRunner())
        payload = json.dumps(report.to_dict(), ensure_ascii=False)
        self.assertIn('"number": "2.1"', payload)


class DefaultProbeTests(unittest.TestCase):
    def test_no_duplicate_section_numbers(self) -> None:
        numbers = [probe.section.number for probe in default_probes()]
        self.assertEqual(len(numbers), len(set(numbers)), "duplicate section numbers in the catalogue")

    def test_every_probe_has_a_command_and_title(self) -> None:
        for probe in default_probes():
            self.assertTrue(probe.command.strip(), probe.section.number)
            self.assertTrue(probe.section.title.strip(), probe.section.number)

    def test_platform_section_exists_and_is_compact(self) -> None:
        numbers = {probe.section.number for probe in default_probes()}
        self.assertIn("6.0", numbers)  # short OS/kernel/arch line
        self.assertNotIn("6.5", numbers)  # /proc/cpuinfo dump removed
        self.assertNotIn("6.6", numbers)  # /proc/meminfo dump removed
        self.assertNotIn("6.7", numbers)  # free -m dump removed


class CustomProbeTests(unittest.TestCase):
    def test_missing_file_keeps_defaults(self) -> None:
        probes = load_custom_probes("/nonexistent/probes.json")
        self.assertTrue(probes)

    def test_custom_probe_replaces_builtin(self) -> None:
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "probes.json"
            path.write_text(
                json.dumps(
                    [
                        {"number": "2.1", "title": "Свой статус", "command": "my-cash status"},
                        {"number": "9.9", "title": "Своя проверка", "command": "echo ok"},
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            probes = load_custom_probes(path)
            by_number = {probe.section.number: probe for probe in probes}
            self.assertEqual(by_number["2.1"].command, "my-cash status")
            self.assertEqual(by_number["2.1"].section.title, "Свой статус")
            self.assertIn("9.9", by_number)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
