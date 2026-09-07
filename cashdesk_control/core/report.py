"""Summary report of a cashier, collected over SSH and rendered for the UI.

The report mirrors the text format the field engineers already use, with one
deliberate difference: the raw ``/proc/cpuinfo``, ``/proc/meminfo``, ``free``
and ``top`` dumps are **not** collected. They ran to several pages per cashier
and told the operator nothing actionable. A single compact platform line (OS,
kernel, architecture, uptime) replaces them.

Every probe is independent: a missing binary or a failed command degrades that
section to "нет данных" instead of aborting the whole report.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, Iterable, Mapping, Sequence

from .models import CommandResult

CommandRunner = Callable[..., Awaitable[CommandResult]]

CASH_HOME = "/home/tc/storage/crystal-cash"
CONF_HOME = "/home/tc/storage/crystal-conf"

STATUS_OK = "ok"
STATUS_EMPTY = "empty"
STATUS_ERROR = "error"
STATUS_SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class ReportOptions:
    """What to collect. Everything expensive or noisy is opt-in."""

    include_jar_versions: bool = False
    include_reboot_history: bool = True
    include_mounts: bool = True
    include_open_files: bool = False
    max_reboot_lines: int = 15
    concurrency: int = 6
    probe_timeout: float = 90.0
    #: Collected but not rendered by default — kept out of the report on purpose.
    include_cpu_details: bool = False
    include_memory_details: bool = False

    def validate(self) -> None:
        if self.concurrency < 1:
            raise ValueError("concurrency must be at least 1")
        if self.probe_timeout <= 0:
            raise ValueError("probe_timeout must be positive")
        if self.max_reboot_lines < 1:
            raise ValueError("max_reboot_lines must be at least 1")


@dataclass(slots=True)
class ReportSection:
    """One numbered block of the report."""

    number: str
    title: str
    body: str = ""
    status: str = STATUS_OK
    level: int = 1
    command: str = ""
    duration_ms: float = 0.0
    error: str | None = None

    @property
    def heading(self) -> str:
        """``[1. Заголовок]`` for level 1, ``[[1.1. ...]]`` for level 2, and so on."""

        opening = "[" * self.level
        closing = "]" * self.level
        return f"{opening}{self.number}. {self.title}{closing}"

    @property
    def is_empty(self) -> bool:
        return self.status == STATUS_EMPTY

    def render(self) -> str:
        lines = [self.heading]
        if self.body.strip():
            lines.append(self.body.rstrip())
        elif self.status == STATUS_ERROR:
            lines.append(f"нет данных ({self.error or 'ошибка сбора'})")
        else:
            lines.append("нет данных")
        return "\n".join(lines)


@dataclass(slots=True)
class ReportProbe:
    """A single shell command that fills one report section."""

    section: ReportSection
    command: str
    timeout: float | None = None
    #: Transform raw stdout into the text stored in the section.
    parser: Callable[[CommandResult], str] | None = None
    #: Skip the probe entirely when the predicate returns ``False``.
    enabled: Callable[[ReportOptions], bool] = lambda _options: True


@dataclass(slots=True)
class KassReport:
    """A collected cashier report."""

    session_name: str
    host: str
    generated_at: datetime
    sections: list[ReportSection] = field(default_factory=list)
    facts: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    duration_ms: float = 0.0

    def section(self, number: str) -> ReportSection | None:
        for section in self.sections:
            if section.number == number:
                return section
        return None

    def fact(self, key: str, default: str = "") -> str:
        return self.facts.get(key, default)

    @property
    def empty_sections(self) -> list[ReportSection]:
        return [section for section in self.sections if section.status == STATUS_EMPTY]

    @property
    def failed_sections(self) -> list[ReportSection]:
        return [section for section in self.sections if section.status == STATUS_ERROR]

    def header_lines(self) -> list[str]:
        stamp = self.generated_at.strftime("%a %d %b %Y %H:%M:%S")
        return [
            stamp,
            "",
            f"Касса: {self.session_name} ({self.host})",
            f"Версия JAVA: {self.fact('java_version') or '—'}",
            f"Версия кассы: {self.fact('cash_version') or '—'}",
            f"ОС: {self.fact('os_release') or '—'}",
            f"Кассовый модуль: {self.fact('module_state') or '—'}",
        ]

    def render_text(self) -> str:
        """Plain-text report in the format the engineers already read."""

        parts = ["\n".join(self.header_lines())]
        for section in self.sections:
            parts.append(section.render())
        if self.errors:
            parts.append("[!] Ошибки сбора\n" + "\n".join(self.errors))
        return "\n\n".join(parts) + "\n"

    def render_markdown(self) -> str:
        """Markdown variant used for the clipboard and ticket exports."""

        lines = [f"# Отчёт по кассе {self.session_name} ({self.host})", ""]
        lines += [f"- {line}" for line in self.header_lines() if line.strip()]
        lines.append("")
        for section in self.sections:
            lines.append(f"{'#' * (section.level + 1)} {section.number}. {section.title}")
            lines.append("")
            body = section.body.strip()
            if body:
                lines += ["```", body, "```", ""]
            else:
                lines += ["_нет данных_", ""]
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_name": self.session_name,
            "host": self.host,
            "generated_at": self.generated_at.isoformat(),
            "duration_ms": self.duration_ms,
            "facts": dict(self.facts),
            "errors": list(self.errors),
            "sections": [
                {
                    "number": section.number,
                    "title": section.title,
                    "level": section.level,
                    "status": section.status,
                    "command": section.command,
                    "duration_ms": section.duration_ms,
                    "error": section.error,
                    "body": section.body,
                }
                for section in self.sections
            ],
        }


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

_PAIR_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 _/()\-]*?)\s*:\s*(.*?)\s*$")

#: Maps ``cash status`` keys onto the report fact names used by the UI cards.
_STATUS_FACTS = {
    "POS Loaded": "pos_loaded",
    "OS Release": "os_release",
    "IP address": "ip_address",
    "Gateway": "gateway",
    "DB Size": "db_size",
    "TCE Path": "tce_path",
    "Disk free": "disk_free",
    "Server IP": "server_ip",
    "Server status": "server_status",
}


def parse_cash_status(text: str) -> dict[str, str]:
    """Extract ``Key : Value`` pairs from the output of ``cash status``."""

    facts: dict[str, str] = {}
    for line in text.splitlines():
        match = _PAIR_RE.match(line)
        if not match:
            continue
        key, value = match.group(1).strip(), match.group(2).strip()
        fact = _STATUS_FACTS.get(key)
        if fact and value:
            facts[fact] = value
    if facts.get("pos_loaded"):
        loaded = facts["pos_loaded"].strip().upper()
        facts["module_state"] = "запущен" if loaded.startswith("Y") else "не запущен"
    return facts


def parse_uptime(text: str) -> str:
    """Human uptime from ``uptime -p`` or the raw ``up X days`` fragment."""

    text = text.strip()
    if not text:
        return ""
    if text.lower().startswith("up "):
        return text
    return text


def first_non_empty(*values: str | None) -> str:
    for value in values:
        if value and value.strip():
            return value.strip()
    return ""


def _tail(result: CommandResult, limit: int) -> str:
    lines = result.output.splitlines()
    return "\n".join(lines[-limit:])


def _strip_blank_runs(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# ---------------------------------------------------------------------------
# Probe catalogue
# ---------------------------------------------------------------------------


def default_probes(options: ReportOptions | None = None) -> list[ReportProbe]:
    """The standard probe set for a SetRetail cashier."""

    options = options or ReportOptions()
    probes: list[ReportProbe] = []

    def add(number: str, title: str, command: str, *, level: int = 1, **kwargs: Any) -> None:
        section = ReportSection(number=number, title=title, command=command, level=level)
        probes.append(ReportProbe(section=section, command=command, **kwargs))

    # 1 — время -------------------------------------------------------------
    add(
        "1",
        "Информация по времени",
        "echo \"Системное время (используется кассовым модулем):\"; date; "
        "echo; echo 'Время BIOS:'; "
        "(sudo hwclock -r 2>/dev/null || cat /sys/class/rtc/rtc0/since_epoch 2>/dev/null || echo 'недоступно без прав root')",
    )

    # 2 — кассовый модуль ----------------------------------------------------
    add(
        "2",
        "Статус работы кассового модуля",
        "if pgrep -f 'crystal-cash|java' >/dev/null 2>&1; then echo 'Кассовый модуль запущен'; "
        "else echo 'Кассовый модуль НЕ запущен'; fi",
    )
    add("2.1", "Общая информация по сборке образа (cash status)", "cash status", level=2)
    add(
        "2.3",
        "Версия кассового модуля и Java",
        "echo -n 'Версия кассы: '; cash version 2>/dev/null || cash --version 2>/dev/null || echo 'не определена'; "
        "echo -n 'Версия JAVA: '; java -version 2>&1 | head -1 || echo 'не определена'",
        level=2,
    )
    add(
        "2.2",
        "Статус работы служб ОФД",
        "for p in socat socat2 comproxy; do if pgrep -x \"$p\" >/dev/null 2>&1; "
        "then echo \"$p is running\"; else echo \"$p is NOT running\"; fi; done; "
        "cat /opt/tce/comproxy/version* 2>/dev/null || true",
        level=2,
    )

    # 3 — размеры ------------------------------------------------------------
    add(
        "3",
        "Размер папок кассового модуля",
        f"du -sh {CASH_HOME} {CASH_HOME}/* 2>/dev/null | sort -h",
        timeout=300.0,
    )
    add(
        "3.1",
        "Размер баз данных",
        f"du -sh {CASH_HOME}/db/* {CASH_HOME}/data/* 2>/dev/null | sort -h; "
        "psql -U postgres -tAc 'select datname, pg_size_pretty(pg_database_size(datname)) "
        "from pg_database order by pg_database_size(datname) desc limit 10' 2>/dev/null",
        level=2,
        timeout=180.0,
    )

    # 4 — данные из кассового модуля -----------------------------------------
    add(
        "4.8",
        "Список загруженных банков",
        f"ls -1 {CASH_HOME}/banks 2>/dev/null",
        level=2,
    )
    add(
        "4.8.2",
        "Папки и файлы банков с указанием прав",
        f"for d in {CASH_HOME}/banks/*/; do [ -d \"$d\" ] || continue; "
        "echo \"[[[ $(basename \"$d\") ]]]\"; ls -lh \"$d\" 2>/dev/null | head -40; echo; done",
        level=2,
        timeout=180.0,
    )
    add(
        "4.9",
        "Список загруженных внешних процессингов",
        f"cat {CASH_HOME}/config/external_processings* 2>/dev/null; "
        f"ls -1 {CASH_HOME}/modules 2>/dev/null | grep -Ei 'bank|sbp|processing|loyal' | head -40",
        level=2,
    )
    add(
        "4.11",
        "Список загруженного оборудования",
        f"ls -1 {CASH_HOME}/modules 2>/dev/null | grep -Ei 'printer|scale|scanner|display|drawer|keyboard|pinpad' | head -40",
        level=2,
    )
    add(
        "4.11.1",
        "Список задействованного оборудования",
        "ls -l /dev/serial/by-id/ 2>/dev/null; echo '---'; lsusb 2>/dev/null | head -30",
        level=2,
    )
    add(
        "4.13",
        "Стыковка с сервером УТМ ЕГАИС",
        f"grep -rhoE 'http://[0-9.]+:[0-9]+/[a-zA-Z?=&]+' {CASH_HOME}/config 2>/dev/null | sort -u | head -10",
        level=2,
    )
    add(
        "4.14",
        "Стыковка с сервером SetRetail",
        f"grep -rhoE '([0-9]{{1,3}}\\.){{3}}[0-9]{{1,3}}' {CASH_HOME}/config 2>/dev/null | sort -u | head -10",
        level=2,
    )

    # 5 — МУК ----------------------------------------------------------------
    add("5.1", "Статус МУКа", "cash muk status 2>/dev/null", level=2)
    add("5.2", "Патчи обновлений", f"du -sh {CONF_HOME}/updates/* 2>/dev/null | sort -h", level=2, timeout=180.0)
    add("5.3", "Бэкапы перед обновлениями", f"du -sh {CONF_HOME}/backups/* 2>/dev/null | sort -h", level=2, timeout=180.0)

    # 6 — платформа и сеть ---------------------------------------------------
    add(
        "6.0",
        "Платформа",
        ". /etc/os-release 2>/dev/null; "
        'echo "ОС: ${PRETTY_NAME:-не определена}"; '
        'echo "Ядро: $(uname -r)"; '
        'echo "Архитектура: $(uname -m)"; '
        'echo "Аптайм: $(uptime -p 2>/dev/null || uptime)"; '
        'echo "Имя узла: $(hostname)"',
        level=2,
    )
    add("6.1", "Информация о сетевых подключениях", "ifconfig -a 2>/dev/null || ip -brief addr", level=2)
    add(
        "6.1.1",
        "Список подключенных хостов к кассе",
        "(ss -tn 2>/dev/null || netstat -tn 2>/dev/null) | awk 'NR>1 {print $5}' | "
        "rev | cut -d: -f2- | rev | sort -u | head -40",
        level=3,
    )
    add(
        "6.1.3",
        "Открытые TCP/UDP порты с именами процессов",
        "sudo ss -tulpen 2>/dev/null || netstat -tulpen 2>/dev/null || ss -tuln",
        level=3,
        timeout=60.0,
    )
    add("6.1.4", "Таблица маршрутизации", "route -n 2>/dev/null || ip route", level=3)
    add(
        "6.2",
        "Статистика перезагрузок ОС",
        f"last reboot 2>/dev/null | head -{options.max_reboot_lines}",
        level=2,
        enabled=lambda opts: opts.include_reboot_history,
    )
    add("6.3", "Используемая версия ядра", "uname -r; cat /proc/version 2>/dev/null", level=2)
    add("6.4", "Архитектура", "uname -m", level=2)
    add(
        "6.8",
        "Смонтированные файловые системы",
        "cat /proc/mounts 2>/dev/null | grep -vE '^(proc|sysfs|cgroup|devpts|tmpfs|nsfs|binfmt)' ",
        level=2,
        enabled=lambda opts: opts.include_mounts,
    )
    add("6.9", "Информация о смонтированных разделах", "df -h -x tmpfs -x devtmpfs -x squashfs 2>/dev/null", level=2)
    add(
        "6.10",
        "Активные COM-порты",
        "setserial -g /dev/ttyS[0-9]* 2>/dev/null | grep -v 'UART: unknown'",
        level=2,
    )
    add("6.11", "USB-подключения", "lsusb 2>/dev/null; echo '---'; ls -l /dev/serial/by-id/ 2>/dev/null", level=2)
    add(
        "6.12",
        "Информация по жестким дискам",
        "lsblk -o NAME,SIZE,TYPE,MODEL,MOUNTPOINT 2>/dev/null; echo '---'; "
        "sudo smartctl -H /dev/sda 2>/dev/null | tail -5",
        level=2,
    )
    add("6.13", "Аппаратные системные компоненты (SMBIOS/DMI)", "sudo dmidecode -t system 2>/dev/null | head -25", level=2)

    # 7 — версии модулей -----------------------------------------------------
    add(
        "7",
        "Версионность jar-файлов кассы (папка modules)",
        f"for f in {CASH_HOME}/modules/*.jar; do "
        "[ -e \"$f\" ] || continue; unzip -p \"$f\" META-INF/MANIFEST.MF 2>/dev/null; echo; done | "
        "grep -E '^(Project|Implementation-Version|Built-Date|Branch):' ",
        timeout=300.0,
        enabled=lambda opts: opts.include_jar_versions,
    )
    return probes


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


class KassReportBuilder:
    """Run the probe catalogue against a session and assemble a report."""

    def __init__(
        self,
        session_name: str,
        host: str,
        probes: Sequence[ReportProbe] | None = None,
        options: ReportOptions | None = None,
    ) -> None:
        self.session_name = session_name
        self.host = host
        self.options = options or ReportOptions()
        self.options.validate()
        self.probes = list(probes) if probes is not None else default_probes(self.options)

    async def collect(
        self,
        run: CommandRunner,
        *,
        progress: Callable[[ReportSection], None] | None = None,
    ) -> KassReport:
        """Execute every enabled probe and return the assembled report."""

        started = _now()
        active = [probe for probe in self.probes if probe.enabled(self.options)]
        semaphore = asyncio.Semaphore(self.options.concurrency)

        async def execute(probe: ReportProbe) -> None:
            timeout = probe.timeout or self.options.probe_timeout
            async with semaphore:
                result = await run(probe.command, timeout=timeout)
            probe.section.command = probe.command
            probe.section.duration_ms = result.duration_ms
            if result.error:
                probe.section.status = STATUS_ERROR
                probe.section.error = result.error
            elif not result.ok:
                probe.section.status = STATUS_ERROR
                detail = result.stderr.strip().splitlines()[0] if result.stderr.strip() else ""
                suffix = f"код возврата {result.exit_code}"
                probe.section.error = f"{detail} ({suffix})" if detail else suffix
                probe.section.body = _strip_blank_runs(result.output)
            else:
                text = probe.parser(result) if probe.parser else result.stdout
                probe.section.body = _strip_blank_runs(text)
                probe.section.status = STATUS_OK if probe.section.body else STATUS_EMPTY
            if progress is not None:
                progress(probe.section)

        await asyncio.gather(*(execute(probe) for probe in active))

        report = KassReport(
            session_name=self.session_name,
            host=self.host,
            generated_at=started,
            sections=[probe.section for probe in self.probes],
            duration_ms=(_now() - started).total_seconds() * 1000.0,
        )
        for probe in self.probes:
            if not probe.enabled(self.options):
                probe.section.status = STATUS_SKIPPED
        _apply_facts(report)
        return report


def _apply_facts(report: KassReport) -> None:
    """Derive the headline facts used by the overview cards and session panel."""

    status = report.section("2.1")
    if status and status.body:
        report.facts.update(parse_cash_status(status.body))

    versions = report.section("2.3")
    if versions and versions.body:
        for line in versions.body.splitlines():
            key, _, value = line.partition(":")
            value = value.strip()
            label = key.strip().lower()
            if label.startswith("версия кассы") and value and "не определена" not in value:
                report.facts["cash_version"] = value
            elif label.startswith("версия java") and value and "не определена" not in value:
                report.facts["java_version"] = value

    platform = report.section("6.0")
    if platform and platform.body:
        for line in platform.body.splitlines():
            key, _, value = line.partition(":")
            value = value.strip()
            if not value:
                continue
            label = key.strip().lower()
            if label.startswith("ос"):
                report.facts.setdefault("os_release", value)
            elif label.startswith("ядро"):
                report.facts["kernel"] = value
            elif label.startswith("архитектур"):
                report.facts["arch"] = value
            elif label.startswith("аптайм"):
                report.facts["uptime"] = parse_uptime(value)
            elif label.startswith("имя узла"):
                report.facts["hostname"] = value

    module = report.section("2")
    if module and module.body:
        report.facts["module_state"] = "запущен" if "запущен" in module.body and "НЕ" not in module.body else "не запущен"

    java = report.section("6.3")
    if java and java.body:
        report.facts.setdefault("kernel", java.body.splitlines()[0].strip())

    if not report.facts.get("cash_version"):
        version = _cash_version(report)
        if version:
            report.facts["cash_version"] = version

    banks = report.section("4.8")
    if banks and banks.body:
        report.facts["banks_count"] = str(len([line for line in banks.body.splitlines() if line.strip()]))

    processings = report.section("4.9")
    if processings and processings.body:
        report.facts["processings_count"] = str(len([line for line in processings.body.splitlines() if line.strip()]))

    ofd = report.section("2.2")
    if ofd and ofd.body:
        report.facts["ofd_state"] = "в норме" if "NOT running" not in ofd.body else "есть остановленные службы"

    for section in report.sections:
        if section.status == STATUS_ERROR and section.error:
            report.errors.append(f"{section.number} {section.title}: {section.error}")


_VERSION_RE = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")


def _cash_version(report: KassReport) -> str:
    """Best-effort cashier build number: jar manifests first, then paths."""

    jars = report.section("7")
    if jars and jars.body:
        versions = _VERSION_RE.findall(jars.body)
        if versions:
            return sorted(versions, key=_version_key)[-1]
    for number in ("2.3", "5.2", "5.3", "3"):
        section = report.section(number)
        if section and section.body:
            versions = _VERSION_RE.findall(section.body)
            if versions:
                return sorted(versions, key=_version_key)[-1]
    return ""


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _now() -> datetime:
    return datetime.now().astimezone()


def load_custom_probes(path: str, base: Sequence[ReportProbe] | None = None) -> list[ReportProbe]:
    """Merge site-specific probes from a JSON file into the default catalogue.

    The file is a list of ``{"number", "title", "command", "level", "timeout"}``
    objects. An entry whose ``number`` matches a built-in probe replaces it, so a
    site can correct one command without editing the application.
    """

    import json
    from pathlib import Path

    probes = list(base) if base is not None else default_probes()
    target = Path(path).expanduser()
    if not target.exists():
        return probes
    raw = json.loads(target.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw = raw.get("probes", [])
    if not isinstance(raw, list):
        raise ReportError(f"{target}: expected a list of probes")
    index = {probe.section.number: position for position, probe in enumerate(probes)}
    for item in raw:
        number = str(item["number"])
        section = ReportSection(
            number=number,
            title=str(item.get("title", number)),
            command=str(item["command"]),
            level=int(item.get("level", 1)),
        )
        probe = ReportProbe(section=section, command=str(item["command"]), timeout=item.get("timeout"))
        if number in index:
            probes[index[number]] = probe
        else:
            probes.append(probe)
    return probes


class ReportError(RuntimeError):
    """Raised when a report definition cannot be read."""


def summarise(report: KassReport) -> Mapping[str, str]:
    """Compact fact map for the session list and the overview cards."""

    keys = (
        "cash_version",
        "module_state",
        "os_release",
        "ip_address",
        "gateway",
        "db_size",
        "disk_free",
        "server_ip",
        "server_status",
        "kernel",
        "arch",
        "uptime",
        "banks_count",
        "processings_count",
        "ofd_state",
    )
    return {key: report.facts[key] for key in keys if report.facts.get(key)}


__all__ = [
    "CASH_HOME",
    "CONF_HOME",
    "KassReport",
    "KassReportBuilder",
    "ReportError",
    "ReportOptions",
    "ReportProbe",
    "ReportSection",
    "STATUS_EMPTY",
    "STATUS_ERROR",
    "STATUS_OK",
    "STATUS_SKIPPED",
    "default_probes",
    "load_custom_probes",
    "parse_cash_status",
    "summarise",
]
