"""Heuristics that decide which flavour of cashier is on the other end.

The classifier only reads data that the report already collected, so it never
issues extra commands and never guesses from hardware the operator's own PC has.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .report import KassReport

_TOUCH_HINTS = ("touch", "elo ", "et1515", "iiyama", " visualizationtouch")
_SCO_HINTS = ("sco", "selfcheckout", "self-checkout", "sco3", "sco4")
_HYBRID_HINTS = ("hybrid", "combo")

#: Module names that imply a given flavour when present in the module list.
_MODULE_HINTS = {
    "SCO": ("sco",),
    "Touch": ("visualizationtouch", "touchcomponents"),
    "Hybrid": ("hybrid",),
}


@dataclass(slots=True)
class Evidence:
    """One reason the classifier leaned towards a flavour."""

    kass_type: str
    weight: int
    reason: str


@dataclass(slots=True)
class DetectionResult:
    kass_type: str
    confidence: float
    evidence: list[Evidence] = field(default_factory=list)
    os_release: str = ""
    version: str = ""
    ip_address: str = ""

    def explain(self) -> str:
        if not self.evidence:
            return "Признаков недостаточно — тип не определён."
        lines = [f"{item.reason} (+{item.weight})" for item in sorted(self.evidence, key=lambda item: -item.weight)]
        return "\n".join(lines)


def classify(report: KassReport) -> DetectionResult:
    """Decide POS / SCO / Touch / Hybrid from the collected report."""

    evidence: list[Evidence] = []
    haystack = "\n".join(section.body for section in report.sections if section.body).lower()

    for hint in _SCO_HINTS:
        if hint in haystack:
            evidence.append(Evidence("SCO", 5, f"в отчёте встречается '{hint}'"))
            break

    for hint in _TOUCH_HINTS:
        if hint in haystack:
            evidence.append(Evidence("Touch", 4, f"найден признак сенсорного монитора: '{hint.strip()}'"))
            break

    for hint in _HYBRID_HINTS:
        if hint in haystack:
            evidence.append(Evidence("Hybrid", 4, f"найден признак гибридной кассы: '{hint}'"))
            break

    modules = report.section("4.11")
    if modules and modules.body:
        lowered = modules.body.lower()
        for kass_type, hints in _MODULE_HINTS.items():
            for hint in hints:
                if hint in lowered:
                    evidence.append(Evidence(kass_type, 3, f"модуль кассового ПО содержит '{hint}'"))
                    break

    hardware = report.section("4.11.1")
    if hardware and hardware.body:
        lowered = hardware.body.lower()
        if "serial" in lowered or "tty" in lowered:
            evidence.append(Evidence("POS", 2, "подключено последовательное кассовое оборудование"))
        if "usb" in lowered:
            evidence.append(Evidence("POS", 1, "оборудование подключено по USB"))

    ports = report.section("6.1.3")
    if ports and ports.body:
        if re.search(r":5900\b|:5901\b", ports.body):
            evidence.append(Evidence("Touch", 2, "открыт порт VNC — касса с графической сессией"))
        if re.search(r":8083\b|:8080\b", ports.body):
            evidence.append(Evidence("POS", 2, "открыт порт кассового модуля (8080/8083)"))

    folders = report.section("3")
    if folders and folders.body:
        if "crystal-cash" in folders.body:
            evidence.append(Evidence("POS", 1, "установлен каталог кассового модуля crystal-cash"))

    scores: dict[str, int] = {}
    for item in evidence:
        scores[item.kass_type] = scores.get(item.kass_type, 0) + item.weight

    if not scores:
        return DetectionResult(
            kass_type="Не определена",
            confidence=0.0,
            evidence=evidence,
            os_release=report.fact("os_release"),
            version=report.fact("cash_version"),
            ip_address=report.fact("ip_address"),
        )

    winner, best = max(scores.items(), key=lambda pair: pair[1])
    total = sum(scores.values()) or 1
    return DetectionResult(
        kass_type=winner,
        confidence=round(best / total, 2),
        evidence=sorted(evidence, key=lambda item: -item.weight),
        os_release=report.fact("os_release"),
        version=report.fact("cash_version"),
        ip_address=report.fact("ip_address"),
    )


def hardware_summary(report: KassReport) -> list[tuple[str, str]]:
    """Short, readable hardware lines for the overview card."""

    rows: list[tuple[str, str]] = []
    facts = report.facts
    if facts.get("os_release"):
        rows.append(("Операционная система", facts["os_release"]))
    if facts.get("kernel"):
        rows.append(("Ядро", facts["kernel"]))
    if facts.get("arch"):
        rows.append(("Архитектура", facts["arch"]))
    if facts.get("hostname"):
        rows.append(("Имя узла", facts["hostname"]))
    if facts.get("uptime"):
        rows.append(("Время работы", facts["uptime"]))

    disks = report.section("6.9")
    if disks and disks.body:
        for line in disks.body.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 6 and parts[0].startswith("/dev/"):
                rows.append((f"Раздел {parts[5]}", f"{parts[1]} всего · {parts[3]} свободно ({parts[4]})"))
                if len([row for row in rows if row[0].startswith("Раздел")]) >= 3:
                    break

    serial = report.section("6.10")
    if serial and serial.body:
        count = len([line for line in serial.body.splitlines() if line.strip()])
        if count:
            rows.append(("COM-порты", f"{count} активных"))

    usb = report.section("6.11")
    if usb and usb.body:
        count = len([line for line in usb.body.splitlines() if line.strip() and line.strip() != "---"])
        if count:
            rows.append(("USB/последовательные устройства", f"{count} записей"))

    return rows
