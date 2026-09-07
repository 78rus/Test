"""Logs module: the application journal plus logs pulled from the cashier.

The left pane is the local journal — every connection, command and error the
application produced, with a level filter and export. The right pane runs the
log commands from the catalogue against the selected cashier, so an operator
can read ``crystal-cash`` logs without typing a single command.
"""

from __future__ import annotations

import logging
from typing import Any

from ...core.asyncio_utils import schedule
from ...core.commands import CommandCatalog

try:
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QComboBox,
        QFileDialog,
        QFrame,
        QHBoxLayout,
        QLabel,
        QListWidget,
        QPlainTextEdit,
        QPushButton,
        QSplitter,
        QVBoxLayout,
        QWidget,
    )

    QT_AVAILABLE = True
except ImportError:  # pragma: no cover - core-only install
    QT_AVAILABLE = False

LEVELS = ("Все", "Информационные", "Предупреждения", "Ошибки")


def _plural(count: int, one: str, few: str, many: str) -> str:
    """Russian pluralisation: 1 запись, 2 записи, 5 записей."""

    remainder100 = count % 100
    if 11 <= remainder100 <= 14:
        form = many
    else:
        remainder10 = count % 10
        form = {1: one, 2: few, 3: few, 4: few}.get(remainder10, many)
    return f"{count} {form}"


if QT_AVAILABLE:

    class LogsPage(QWidget):
        """Journal viewer and remote log fetcher."""

        commandRequested = Signal(str)  # command id
        statusMessage = Signal(str)

        def __init__(self, catalog: CommandCatalog | None = None, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self._catalog = catalog
            self._entries: list[tuple[str, str]] = []  # (level, line)
            self._logger = logging.getLogger("cashdesk_control.logs")
            self._build_ui()
            if catalog is not None:
                self.set_catalog(catalog)

        # -- ui -----------------------------------------------------------
        def _build_ui(self) -> None:
            layout = QHBoxLayout(self)
            layout.setContentsMargins(16, 14, 16, 16)
            layout.setSpacing(14)

            splitter = QSplitter(Qt.Orientation.Horizontal)

            # journal pane
            journal_frame = QFrame(objectName="panel")
            journal_layout = QVBoxLayout(journal_frame)
            journal_layout.setContentsMargins(14, 12, 14, 14)
            journal_layout.setSpacing(8)
            journal_layout.addWidget(QLabel("ЖУРНАЛ ПРИЛОЖЕНИЯ", objectName="panelEyebrow"))

            controls = QHBoxLayout()
            self.level_filter = QComboBox()
            self.level_filter.addItems(LEVELS)
            self.level_filter.currentTextChanged.connect(lambda _: self._render())
            controls.addWidget(QLabel("Показать:", objectName="dim"))
            controls.addWidget(self.level_filter)
            controls.addStretch()
            self.journal_count = QLabel(_plural(0, "запись", "записи", "записей"), objectName="dim")
            controls.addWidget(self.journal_count)
            journal_layout.addLayout(controls)

            self.journal_view = QPlainTextEdit()
            self.journal_view.setObjectName("terminalOutput")
            self.journal_view.setReadOnly(True)
            self.journal_view.setMaximumBlockCount(5000)
            journal_layout.addWidget(self.journal_view, 1)

            actions = QHBoxLayout()
            copy_button = QPushButton("Копировать", objectName="secondary")
            copy_button.clicked.connect(self._copy_journal)
            save_button = QPushButton("Сохранить…", objectName="secondary")
            save_button.clicked.connect(self._save_journal)
            clear_button = QPushButton("Очистить", objectName="secondary")
            clear_button.clicked.connect(self.clear)
            for button in (copy_button, save_button, clear_button):
                actions.addWidget(button)
            actions.addStretch()
            journal_layout.addLayout(actions)

            # remote pane
            remote_frame = QFrame(objectName="panel")
            remote_layout = QVBoxLayout(remote_frame)
            remote_layout.setContentsMargins(14, 12, 14, 14)
            remote_layout.setSpacing(8)
            remote_layout.addWidget(QLabel("ЛОГИ С КАССЫ", objectName="panelEyebrow"))
            hint = QLabel("Выберите кассу и запрос — команда выполняется по SSH, вывод показывается ниже.", objectName="muted")
            hint.setWordWrap(True)
            remote_layout.addWidget(hint)

            self.command_list = QListWidget()
            self.command_list.setObjectName("commandList")
            self.command_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            remote_layout.addWidget(self.command_list, 1)

            run_row = QHBoxLayout()
            self.run_button = QPushButton("Выполнить", objectName="primary")
            self.run_button.setEnabled(False)
            self.run_button.clicked.connect(self._run_selected)
            run_row.addWidget(self.run_button)
            run_row.addStretch()
            remote_layout.addLayout(run_row)

            self.remote_output = QPlainTextEdit()
            self.remote_output.setObjectName("terminalOutput")
            self.remote_output.setReadOnly(True)
            self.remote_output.setPlaceholderText("Здесь появится вывод команды с кассы.")
            remote_layout.addWidget(self.remote_output, 1)

            splitter.addWidget(journal_frame)
            splitter.addWidget(remote_frame)
            splitter.setStretchFactor(0, 3)
            splitter.setStretchFactor(1, 2)
            layout.addWidget(splitter)

        # -- commands -------------------------------------------------------
        def set_catalog(self, catalog: CommandCatalog) -> None:
            """Populate the list with the catalogue's log commands."""

            self._catalog = catalog
            self.command_list.clear()
            for spec in catalog.by_category().get("Логи", []):
                item_text = f"{spec.label}"
                self.command_list.addItem(item_text)
                self.command_list.item(self.command_list.count() - 1).setData(Qt.ItemDataRole.UserRole, spec.id)
            self.command_list.itemSelectionChanged.connect(self._selection_changed)
            self._selection_changed()

        def _selection_changed(self) -> None:
            self.run_button.setEnabled(self.command_list.currentItem() is not None)

        def _run_selected(self) -> None:
            item = self.command_list.currentItem()
            if item is None or self._catalog is None:
                return
            spec_id = str(item.data(Qt.ItemDataRole.UserRole))
            self.commandRequested.emit(spec_id)

        # -- journal ----------------------------------------------------------
        def append(self, message: str, *, level: str = "info") -> None:
            from datetime import datetime

            stamp = datetime.now().strftime("%H:%M:%S")
            self._entries.append((level, f"{stamp}  {message}"))
            if len(self._entries) > 5000:
                del self._entries[: len(self._entries) - 5000]
            if self._passes(level):
                self.journal_view.appendPlainText(self._entries[-1][1])
            self.journal_count.setText(_plural(len(self._entries), "запись", "записи", "записей"))

        def clear(self) -> None:
            self._entries.clear()
            self.journal_view.clear()
            self.journal_count.setText(_plural(0, "запись", "записи", "записей"))

        def _passes(self, level: str) -> bool:
            wanted = self.level_filter.currentText()
            if wanted == "Все":
                return True
            return {
                "Информационные": level in ("info", "ok"),
                "Предупреждения": level == "warn",
                "Ошибки": level == "error",
            }.get(wanted, True)

        def _render(self) -> None:
            self.journal_view.clear()
            for level, line in self._entries:
                if self._passes(level):
                    self.journal_view.appendPlainText(line)

        def _copy_journal(self) -> None:
            from PySide6.QtWidgets import QApplication

            QApplication.clipboard().setText(self.journal_view.toPlainText())
            self.statusMessage.emit("Журнал скопирован в буфер обмена")

        def _save_journal(self) -> None:
            path, _ = QFileDialog.getSaveFileName(self, "Сохранить журнал", "cashdesk-journal.log", "Логи (*.log *.txt)")
            if not path:
                return
            try:
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(self.journal_view.toPlainText())
            except OSError as exc:
                self._logger.error("journal could not be saved: %s", exc)
                self.statusMessage.emit(f"Не удалось сохранить журнал: {exc}")
                return
            self.statusMessage.emit(f"Журнал сохранён: {path}")

        # -- remote output -----------------------------------------------------
        def show_remote(self, title: str, text: str) -> None:
            self.remote_output.setPlainText(f"# {title}\n\n{text}" if text else f"# {title}\n\n(пусто)")

        def set_busy(self, busy: bool) -> None:
            self.run_button.setEnabled(not busy and self.command_list.currentItem() is not None)
            if busy:
                self.remote_output.setPlainText("Выполняется…")

        def set_available(self, available: bool, hint: str = "") -> None:
            self.command_list.setEnabled(available)
            self.run_button.setEnabled(available and self.command_list.currentItem() is not None)
            if hint:
                self.remote_output.setPlaceholderText(hint)


__all__ = ["LogsPage", "LEVELS", "QT_AVAILABLE"]
