"""Catalogue of shell commands executed on a cashier by pressing a button.

Every command the UI can run is described by a :class:`CommandSpec`. The default
catalogue covers the operations a field engineer performs on a SetRetail
cashier; additional entries can be loaded from ``commands.json`` so new
procedures do not require a code change.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping


class Risk(str, Enum):
    """How much damage a command can do if it is pressed by accident."""

    SAFE = "safe"
    CAUTION = "caution"
    DANGER = "danger"
    CRITICAL = "critical"


RISK_LABELS: dict[Risk, str] = {
    Risk.SAFE: "Безопасно",
    Risk.CAUTION: "Осторожно",
    Risk.DANGER: "Опасно",
    Risk.CRITICAL: "Критично",
}


@dataclass(frozen=True, slots=True)
class CommandSpec:
    """One executable button in the session workspace."""

    id: str
    label: str
    command: str
    category: str = "Диагностика"
    risk: Risk = Risk.SAFE
    description: str = ""
    timeout: float = 60.0
    needs_sudo: bool = False
    confirm: bool = False
    #: Push the output into the session journal instead of a popup.
    inline: bool = True
    #: Refresh the summary report once the command has finished.
    refresh_report: bool = False
    icon: str = "▶"

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("command id must not be empty")
        if not self.label.strip():
            raise ValueError("command label must not be empty")
        if not self.command.strip():
            raise ValueError("command must not be empty")
        object.__setattr__(self, "risk", Risk(self.risk))
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")

    @property
    def is_destructive(self) -> bool:
        return self.risk in {Risk.DANGER, Risk.CRITICAL}

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["risk"] = self.risk.value
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CommandSpec":
        return cls(
            id=str(data["id"]),
            label=str(data["label"]),
            command=str(data["command"]),
            category=str(data.get("category", "Диагностика")),
            risk=Risk(data.get("risk", Risk.SAFE.value)),
            description=str(data.get("description", "")),
            timeout=float(data.get("timeout", 60.0)),
            needs_sudo=bool(data.get("needs_sudo", False)),
            confirm=bool(data.get("confirm", False)),
            inline=bool(data.get("inline", True)),
            refresh_report=bool(data.get("refresh_report", False)),
            icon=str(data.get("icon", "▶")),
        )


#: Paths that hold the cashier payload on a standard SetRetail image.
CASH_HOME = "/home/tc/storage/crystal-cash"
CONF_HOME = "/home/tc/storage/crystal-conf"


DEFAULT_COMMANDS: tuple[CommandSpec, ...] = (
    # -- Кассовый модуль -----------------------------------------------------
    CommandSpec(
        id="cash_status",
        label="Статус кассы",
        command="cash status",
        category="Кассовый модуль",
        description="Показать состояние кассового модуля (cash status).",
        icon="▦",
        refresh_report=True,
    ),
    CommandSpec(
        id="cash_restart",
        label="Перезапустить кассу",
        command="cash restart",
        category="Кассовый модуль",
        risk=Risk.DANGER,
        confirm=True,
        description="Перезапуск кассового модуля: cash restart. Касса недоступна ~1–2 минуты.",
        icon="↻",
        refresh_report=True,
    ),
    CommandSpec(
        id="full_reboot",
        label="Полная перезагрузка",
        command="sudo reboot",
        category="Кассовый модуль",
        risk=Risk.CRITICAL,
        confirm=True,
        needs_sudo=True,
        timeout=20.0,
        description="Полная перезагрузка операционной системы: sudo reboot. SSH-сессия оборвётся.",
        icon="⏻",
        refresh_report=True,
    ),
    CommandSpec(
        id="cash_processes",
        label="Процессы кассы",
        command="ps -eo pid,user,pcpu,pmem,etime,comm,args --sort=-pmem | grep -Ei 'java|crystal|comproxy|socat' | grep -v grep | head -25",
        category="Кассовый модуль",
        description="Процессы кассового модуля, ОФД и прокси.",
        icon="⌁",
    ),
    # -- ОФД и сервисы ------------------------------------------------------
    CommandSpec(
        id="ofd_status",
        label="Службы ОФД",
        command=(
            "for p in socat socat2 comproxy; do "
            "if pgrep -x \"$p\" >/dev/null 2>&1; then echo \"$p is running\"; "
            "else echo \"$p is NOT running\"; fi; done"
        ),
        category="ОФД и сервисы",
        description="Проверка socat/socat2/comproxy.",
        icon="⇄",
    ),
    CommandSpec(
        id="ofd_restart",
        label="Перезапустить ОФД",
        command="sudo systemctl restart comproxy socat socat2 2>&1 | tail -5",
        category="ОФД и сервисы",
        risk=Risk.DANGER,
        confirm=True,
        needs_sudo=True,
        description="Перезапуск служб передачи фискальных данных.",
        icon="↻",
    ),
    # -- Диски и хранилище --------------------------------------------------
    CommandSpec(
        id="disk_free",
        label="Свободное место",
        command="df -h -x tmpfs -x devtmpfs -x squashfs -x overlay 2>/dev/null | head -15",
        category="Диски и хранилище",
        description="Заполнение разделов кассы.",
        icon="▤",
    ),
    CommandSpec(
        id="cash_folders",
        label="Размер папок кассы",
        command=f"du -sh {CASH_HOME} {CASH_HOME}/* 2>/dev/null | sort -h",
        category="Диски и хранилище",
        timeout=180.0,
        description="Размер каталогов кассового модуля.",
        icon="▧",
    ),
    CommandSpec(
        id="backups",
        label="Бэкапы и патчи",
        command=f"du -sh {CONF_HOME}/backups/* {CONF_HOME}/updates/* 2>/dev/null | sort -h | tail -20",
        category="Диски и хранилище",
        timeout=180.0,
        description="Бэкапы перед обновлениями и скачанные патчи.",
        icon="⛁",
    ),
    # -- Сеть ---------------------------------------------------------------
    CommandSpec(
        id="net_addr",
        label="Сетевые интерфейсы",
        command="ip -brief addr 2>/dev/null || ifconfig -a",
        category="Сеть",
        description="Адреса интерфейсов кассы.",
        icon="⇶",
    ),
    CommandSpec(
        id="net_ports",
        label="Открытые порты",
        command="sudo ss -tulpen 2>/dev/null || netstat -tulpen 2>/dev/null",
        category="Сеть",
        needs_sudo=True,
        description="Слушающие TCP/UDP порты с процессами.",
        icon="⚯",
    ),
    CommandSpec(
        id="net_route",
        label="Маршрутизация",
        command="ip route 2>/dev/null || route -n",
        category="Сеть",
        description="Таблица маршрутов.",
        icon="➤",
    ),
    CommandSpec(
        id="ping_server",
        label="Пинг сервера",
        command="ping -c 3 -W 2 $(grep -oE '([0-9]{1,3}\\.){3}[0-9]{1,3}' /etc/hosts | head -1) 2>&1 | tail -5",
        category="Сеть",
        timeout=30.0,
        description="Проверка доступности сервера SetRetail.",
        icon="◉",
    ),
    # -- Логи ---------------------------------------------------------------
    CommandSpec(
        id="tail_cash_log",
        label="Хвост лога кассы",
        command=f"tail -n 120 {CASH_HOME}/logs/cash.log 2>/dev/null || ls -lh {CASH_HOME}/logs | head -20",
        category="Логи",
        timeout=30.0,
        description="Последние записи журнала кассового модуля.",
        icon="≡",
    ),
    CommandSpec(
        id="log_errors",
        label="Ошибки за сегодня",
        command=(
            f"grep -hEi 'error|exception|fatal' {CASH_HOME}/logs/*.log 2>/dev/null | tail -60"
        ),
        category="Логи",
        timeout=90.0,
        description="Строки с ошибками из журналов кассы.",
        icon="⚠",
    ),
    CommandSpec(
        id="journal_system",
        label="Системный журнал",
        command="sudo journalctl -n 150 --no-pager 2>/dev/null | tail -120",
        category="Логи",
        needs_sudo=True,
        timeout=60.0,
        description="Последние записи journalctl.",
        icon="≣",
    ),
    # -- Оборудование -------------------------------------------------------
    CommandSpec(
        id="hw_usb",
        label="USB-устройства",
        command="lsusb 2>/dev/null; echo '---'; ls -l /dev/serial/by-id/ 2>/dev/null",
        category="Оборудование",
        description="USB-устройства и последовательные порты по ID.",
        icon="⎁",
    ),
    CommandSpec(
        id="hw_serial",
        label="COM-порты",
        command="setserial -g /dev/ttyS[0-9]* 2>/dev/null | grep -v 'UART: unknown'",
        category="Оборудование",
        description="Активные последовательные порты.",
        icon="⌁",
    ),
    CommandSpec(
        id="hw_platform",
        label="Платформа",
        command=(
            ". /etc/os-release 2>/dev/null; "
            'echo "ОС: $PRETTY_NAME"; '
            'echo "Ядро: $(uname -r)"; '
            'echo "Архитектура: $(uname -m)"; '
            'echo "Аптайм: $(uptime -p 2>/dev/null)"'
        ),
        category="Оборудование",
        description="ОС, ядро, архитектура и время работы.",
        icon="◈",
    ),
    # -- База данных --------------------------------------------------------
    CommandSpec(
        id="db_size",
        label="Размер базы",
        command=(
            "psql -U postgres -tAc \"select pg_size_pretty(sum(pg_database_size(datname))) from pg_database\" "
            "2>&1 | tail -3"
        ),
        category="База данных",
        timeout=30.0,
        description="Суммарный размер баз PostgreSQL на кассе.",
        icon="▥",
    ),
    CommandSpec(
        id="db_connections",
        label="Соединения с БД",
        command="psql -U postgres -c 'select pid, usename, state, query_start from pg_stat_activity limit 20' 2>&1 | tail -25",
        category="База данных",
        timeout=30.0,
        description="Активные подключения к PostgreSQL.",
        icon="⇉",
    ),
)


class CommandCatalog:
    """Ordered, editable collection of :class:`CommandSpec` objects."""

    def __init__(self, specs: Iterable[CommandSpec] = ()) -> None:
        self._specs: dict[str, CommandSpec] = {}
        self._order: list[str] = []
        for spec in specs:
            self.add(spec)

    @classmethod
    def defaults(cls) -> "CommandCatalog":
        return cls(DEFAULT_COMMANDS)

    def add(self, spec: CommandSpec) -> None:
        if spec.id not in self._specs:
            self._order.append(spec.id)
        self._specs[spec.id] = spec

    def remove(self, spec_id: str) -> None:
        if spec_id in self._specs:
            del self._specs[spec_id]
            self._order.remove(spec_id)

    def get(self, spec_id: str) -> CommandSpec:
        try:
            return self._specs[spec_id]
        except KeyError as exc:
            raise CommandNotFoundError(spec_id) from exc

    def __contains__(self, spec_id: object) -> bool:
        return spec_id in self._specs

    def __len__(self) -> int:
        return len(self._specs)

    def __iter__(self):
        return (self._specs[spec_id] for spec_id in self._order if spec_id in self._specs)

    def by_category(self) -> dict[str, list[CommandSpec]]:
        grouped: dict[str, list[CommandSpec]] = {}
        for spec in self:
            grouped.setdefault(spec.category, []).append(spec)
        return grouped

    def to_list(self) -> list[dict[str, Any]]:
        return [spec.to_dict() for spec in self]

    def save(self, path: str | Path) -> None:
        target = Path(path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_list(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path, *, base: "CommandCatalog | None" = None) -> "CommandCatalog":
        """Load a catalogue, optionally extending *base* (defaults to built-ins).

        Entries with an existing id replace the built-in ones, which lets a site
        tweak a command without losing the rest of the catalogue. A missing file
        is not an error — the base catalogue is returned unchanged.
        """

        catalog = base or cls.defaults()
        target = Path(path).expanduser()
        if not target.exists():
            return catalog
        raw = json.loads(target.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            raw = raw.get("commands", [])
        if not isinstance(raw, list):
            raise CommandCatalogError(f"{target}: expected a list of commands")
        for item in raw:
            catalog.add(CommandSpec.from_dict(item))
        return catalog


def sudo_wrap(spec: CommandSpec, *, quote_style: str = "'") -> str:
    """Return *spec.command* wrapped for non-interactive ``sudo -S``.

    Only commands whose first token already is ``sudo`` are wrapped; the
    password itself is fed through stdin by the transport, never embedded in the
    command line where it would end up in ``ps`` output or shell history.
    """

    command = spec.command.strip()
    if not command.startswith("sudo "):
        return command
    return command.replace("sudo ", "sudo -S -p '' ", 1)


def describe_risk(spec: CommandSpec) -> str:
    return f"{RISK_LABELS[spec.risk]} · {spec.description or spec.command}"


def spec_with(spec: CommandSpec, **changes: Any) -> CommandSpec:
    return replace(spec, **changes)


class CommandCatalogError(RuntimeError):
    """Raised for an unreadable command catalogue."""


class CommandNotFoundError(CommandCatalogError):
    """Raised when an unknown command id is requested."""
