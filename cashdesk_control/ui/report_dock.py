"""The summary report shown in the window next to the workspace."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..core.report import (
    STATUS_EMPTY,
    STATUS_ERROR,
    STATUS_OK,
    STATUS_SKIPPED,
    KassReport,
    ReportSection,
)

try:
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtWidgets import (
        QCheckBox,
        QDockWidget,
        QFileDialog,
        QHBoxLayout,
        QLabel,
        QListWidget,
        QListWidgetItem,
        QMessageBox,
        QPlainTextEdit,
        QProgressBar,
        QPushButton,
        QSplitter,
        QVBoxLayout,
        QWidget,
    )
except ImportError:  # pragma: no cover
    QT_AVAILABLE = False
else:
    QT_AVAILABLE = True

logger = logging.getLogger("cashdesk_control.report")


if QT_AVAILABLE:

    class ReportDock(QDockWidget):
        """Dockable report panel — can also be detached into its own window."""

        refreshRequested = Signal()
        statusMessage = Signal(str)

        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__("Сводный отчёт по кассе", parent)
            self.setObjectName("reportDock")
            self.setFeatures(
                QDockWidget.DockWidgetFeature.DockWidgetClosable
                | QDockWidget.DockWidgetFeature.DockWidgetMovable
                | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            )
            self.setMinimumWidth(430)
            self._sections: list[ReportSection] = []

            container = QWidget()
            layout = QVBoxLayout(container)
            layout.setContentsMargins(10, 10, 10, 10)
            layout.setSpacing(8)

            head = QHBoxLayout()
            head.setSpacing(6)
            self.title = QLabel("Отчёт не собран", objectName="sectionTitle")
            head.addWidget(self.title)
            head.addStretch()
            self.update_button = QPushButton("↻ Собрать отчёт", objectName="primary")
            self.update_button.clicked.connect(self.refreshRequested.emit)
            head.addWidget(self.update_button)
            layout.addLayout(head)

            self.meta = QLabel("Выберите кассу и нажмите «Собрать отчёт».", objectName="dim")
            self.meta.setWordWrap(True)
            layout.addWidget(self.meta)

            self.progress = QProgressBar()
            self.progress.setRange(0, 0)
            self.progress.setVisible(False)
            layout.addWidget(self.progress)

            options = QHBoxLayout()
            options.setSpacing(12)
            self.opt_jars = QCheckBox("Версии jar-модулей")
            self.opt_jars.setToolTip("Долгий сбор: распаковывает MANIFEST.MF каждого модуля")
            self.opt_reboots = QCheckBox("История перезагрузок")
            self.opt_reboots.setChecked(True)
            self.opt_mounts = QCheckBox("Точки монтирования")
            self.opt_mounts.setChecked(True)
            options.addWidget(self.opt_jars)
            options.addWidget(self.opt_reboots)
            options.addWidget(self.opt_mounts)
            options.addStretch()
            layout.addLayout(options)

            splitter = QSplitter(Qt.Orientation.Horizontal)
            self.sections = QListWidget()
            self.sections.setMinimumWidth(190)
            self.sections.currentRowChanged.connect(self._section_selected)
            splitter.addWidget(self.sections)

            self.body = QPlainTextEdit()
            self.body.setObjectName("reportView")
            self.body.setReadOnly(True)
            self.body.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
            splitter.addWidget(self.body)
            splitter.setSizes([220, 460])
            layout.addWidget(splitter, 1)

            actions = QHBoxLayout()
            actions.setSpacing(6)
            full = QPushButton("Полный текст", objectName="secondary")
            full.clicked.connect(self.show_full_text)
            actions.addWidget(full)
            copy = QPushButton("Копировать", objectName="secondary")
            copy.clicked.connect(self.copy_current)
            actions.addWidget(copy)
            save = QPushButton("Сохранить в файл…", objectName="secondary")
            save.clicked.connect(self.save_report)
            actions.addWidget(save)
            actions.addStretch()
            layout.addLayout(actions)

            self.setWidget(container)
            self._report: KassReport | None = None

        # -- state ---------------------------------------------------------------
        @property
        def options(self) -> dict[str, bool]:
            return {
                "include_jar_versions": self.opt_jars.isChecked(),
                "include_reboot_history": self.opt_reboots.isChecked(),
                "include_mounts": self.opt_mounts.isChecked(),
            }

        def set_busy(self, busy: bool, message: str = "") -> None:
            self.progress.setVisible(busy)
            self.update_button.setEnabled(not busy)
            if message:
                self.meta.setText(message)

        def set_report(self, report: KassReport) -> None:
            self._report = report
            self._sections = list(report.sections)
            self.title.setText(f"{report.session_name} · {report.host}")
            collected = len([section for section in report.sections if section.status not in (STATUS_EMPTY, STATUS_SKIPPED)])
            parts = [
                f"Собран за {report.duration_ms / 1000:.1f} с",
                f"разделов с данными: {collected}",
            ]
            if report.fact("cash_version"):
                parts.append(f"версия кассы {report.fact('cash_version')}")
            if report.fact("os_release"):
                parts.append(report.fact("os_release"))
            if report.failed_sections:
                parts.append(f"ошибок: {len(report.failed_sections)}")
            self.meta.setText(" · ".join(parts))
            self._render_index()
            self.set_busy(False)

        def _render_index(self) -> None:
            self.sections.clear()
            for section in self._sections:
                marker = {STATUS_OK: "✓", STATUS_EMPTY: "·", STATUS_ERROR: "!", STATUS_SKIPPED: "—"}.get(section.status, "·")
                indent = "    " * (section.level - 1)
                item = QListWidgetItem(f"{marker} {indent}{section.number}. {section.title}")
                item.setToolTip(section.command)
                self.sections.addItem(item)
            if self.sections.count():
                self.sections.setCurrentRow(0)

        def _section_selected(self, row: int) -> None:
            if row < 0 or row >= len(self._sections):
                return
            section = self._sections[row]
            header = f"{section.heading}\n$ {section.command}\n" + ("—" * 60) + "\n"
            if section.body.strip():
                self.body.setPlainText(header + section.body)
            elif section.error:
                self.body.setPlainText(header + f"нет данных: {section.error}")
            else:
                self.body.setPlainText(header + "нет данных")

        def show_full_text(self) -> None:
            if self._report is None:
                self.statusMessage.emit("Отчёт ещё не собран")
                return
            self.body.setPlainText(self._report.render_text())

        def copy_current(self) -> None:
            from PySide6.QtWidgets import QApplication

            if self._report is None:
                return
            QApplication.clipboard().setText(self.body.toPlainText())
            self.statusMessage.emit("Отчёт скопирован в буфер обмена")

        def save_report(self) -> None:
            if self._report is None:
                self.statusMessage.emit("Отчёт ещё не собран")
                return
            default = f"report_{self._report.host.replace(':', '_')}_{self._report.generated_at:%Y%m%d_%H%M%S}.txt"
            path, selected = QFileDialog.getSaveFileName(
                self,
                "Сохранить отчёт",
                default,
                "Текст (*.txt);;Markdown (*.md)",
            )
            if not path:
                return
            content = self._report.render_markdown() if path.endswith(".md") else self._report.render_text()
            try:
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(content)
                self.statusMessage.emit(f"Отчёт сохранён: {path}")
            except OSError as exc:
                QMessageBox.warning(self, "Не удалось сохранить", str(exc))

        def clear(self) -> None:
            self._report = None
            self._sections = []
            self.sections.clear()
            self.body.clear()
            self.title.setText("Отчёт не собран")
            self.meta.setText("Выберите кассу и нажмите «Собрать отчёт».")

else:

    class ReportDock:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PySide6 is required for the report dock")
