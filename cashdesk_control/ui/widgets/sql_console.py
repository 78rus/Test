"""SQL console: schema tree, editor, result grid and CSV export."""

from __future__ import annotations

import logging
from typing import Any

from ...core.asyncio_utils import schedule
from ...core.db_client import DatabaseClient, QueryResult

try:
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtGui import QKeySequence, QShortcut
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QFileDialog,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QPlainTextEdit,
        QPushButton,
        QSplitter,
        QTableWidget,
        QTableWidgetItem,
        QTreeWidget,
        QTreeWidgetItem,
        QVBoxLayout,
        QWidget,
    )
except ImportError:  # pragma: no cover
    QT_AVAILABLE = False
else:
    QT_AVAILABLE = True

logger = logging.getLogger("cashdesk_control.sql")


if QT_AVAILABLE:

    class SqlConsoleWidget(QWidget):
        """Browse the cashier database and run statements against it."""

        statusMessage = Signal(str)
        connectRequested = Signal()

        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self._client: DatabaseClient | None = None
            layout = QVBoxLayout(self)
            layout.setContentsMargins(12, 12, 12, 12)
            layout.setSpacing(8)

            bar = QHBoxLayout()
            bar.setSpacing(6)
            self.state = QLabel("база не подключена", objectName="dim")
            bar.addWidget(self.state)
            bar.addStretch()
            connect = QPushButton("Подключить БД", objectName="primary")
            connect.clicked.connect(self.connectRequested.emit)
            bar.addWidget(connect)
            layout.addLayout(bar)

            splitter = QSplitter(Qt.Orientation.Horizontal)

            self.schema = QTreeWidget()
            self.schema.setHeaderLabels(["Схема / таблица"])
            self.schema.setMinimumWidth(220)
            self.schema.itemDoubleClicked.connect(self._preview_table)
            splitter.addWidget(self.schema)

            right = QWidget()
            right_layout = QVBoxLayout(right)
            right_layout.setContentsMargins(0, 0, 0, 0)
            right_layout.setSpacing(6)

            self.editor = QPlainTextEdit()
            self.editor.setObjectName("sqlEditor")
            self.editor.setPlaceholderText("SELECT …  ·  Ctrl+Enter — выполнить")
            self.editor.setPlainText("select 1 as ok;")
            right_layout.addWidget(self.editor, 1)

            actions = QHBoxLayout()
            actions.setSpacing(6)
            run = QPushButton("▶ Выполнить  (Ctrl+Enter)", objectName="primary")
            run.clicked.connect(self.execute_current)
            actions.addWidget(run)
            export = QPushButton("Экспорт в CSV", objectName="secondary")
            export.clicked.connect(self.export_csv)
            actions.addWidget(export)
            clear = QPushButton("Очистить", objectName="secondary")
            clear.clicked.connect(lambda: self.editor.clear())
            actions.addWidget(clear)
            actions.addStretch()
            self.timing = QLabel("", objectName="dim")
            actions.addWidget(self.timing)
            right_layout.addLayout(actions)

            self.grid = QTableWidget(0, 0)
            self.grid.setAlternatingRowColors(True)
            self.grid.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            self.grid.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            right_layout.addWidget(self.grid, 2)
            splitter.addWidget(right)
            splitter.setSizes([260, 720])
            layout.addWidget(splitter, 1)

            QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.execute_current)

        # -- wiring --------------------------------------------------------------
        def set_client(self, client: DatabaseClient | None, label: str = "") -> None:
            self._client = client
            if client is None:
                self.state.setText("база не подключена")
                self.schema.clear()
                return
            self.state.setText(label or "подключено")
            self.refresh_schema()

        def refresh_schema(self) -> None:
            schedule(self._refresh_schema_async())

        async def _refresh_schema_async(self) -> None:
            client = self._client
            if client is None:
                return
            try:
                tables = await client.list_tables_async()
            except Exception as exc:
                self.state.setText(f"ошибка: {exc}")
                return
            self.schema.clear()
            groups: dict[str, QTreeWidgetItem] = {}
            for table in tables:
                key = table.schema or "(по умолчанию)"
                if key not in groups:
                    groups[key] = QTreeWidgetItem(self.schema, [key])
                item = QTreeWidgetItem(groups[key], [f"{table.name}  ({table.kind})"])
                item.setData(0, Qt.ItemDataRole.UserRole, (table.schema, table.name))
            self.schema.expandToDepth(0)
            self.statusMessage.emit(f"Схема обновлена: {len(tables)} объектов")

        # -- execution ------------------------------------------------------------
        def execute_current(self) -> None:
            sql = self.editor.toPlainText().strip().rstrip(";")
            if not sql:
                return
            schedule(self._execute_async(sql))

        async def _execute_async(self, sql: str) -> None:
            client = self._client
            if client is None:
                self.statusMessage.emit("Сначала подключитесь к базе")
                return
            result = await client.execute_async(sql)
            self.render_result(result)

        def render_result(self, result: QueryResult) -> None:
            self.timing.setText(f"{result.duration_ms:.0f} мс · строк: {len(result.rows)}")
            if result.error:
                self.grid.clear()
                self.grid.setColumnCount(1)
                self.grid.setHorizontalHeaderLabels(["Ошибка"])
                self.grid.setRowCount(1)
                self.grid.setItem(0, 0, QTableWidgetItem(result.error))
                self.statusMessage.emit(f"Ошибка SQL: {result.error}")
                return
            self.grid.clear()
            self.grid.setColumnCount(len(result.columns))
            self.grid.setHorizontalHeaderLabels(result.columns)
            self.grid.setRowCount(len(result.rows))
            for row_index, row in enumerate(result.rows):
                for column_index, value in enumerate(row):
                    item = QTableWidgetItem("" if value is None else str(value))
                    item.setToolTip(type(value).__name__)
                    self.grid.setItem(row_index, column_index, item)
            self.grid.resizeColumnsToContents()
            header = self.grid.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            header.setStretchLastSection(True)
            self.statusMessage.emit(f"Выполнено за {result.duration_ms:.0f} мс, строк: {len(result.rows)}")

        def _preview_table(self, item: QTreeWidgetItem, _column: int) -> None:
            payload = item.data(0, Qt.ItemDataRole.UserRole)
            if not payload or self._client is None:
                return
            schema, table = payload
            schedule(self._preview_async(schema, table))

        async def _preview_async(self, schema: str, table: str) -> None:
            client = self._client
            if client is None:
                return
            result = await client.preview_table(table, schema)
            self.editor.setPlainText(result.sql)
            self.render_result(result)

        def export_csv(self) -> None:
            if self.grid.rowCount() == 0:
                self.statusMessage.emit("Нет данных для экспорта")
                return
            path, _ = QFileDialog.getSaveFileName(self, "Экспорт результата", "query_result.csv", "CSV (*.csv)")
            if not path:
                return
            columns = [self.grid.horizontalHeaderItem(index).text() for index in range(self.grid.columnCount())]
            rows: list[list[str]] = []
            for row_index in range(self.grid.rowCount()):
                rows.append([self.grid.item(row_index, column).text() if self.grid.item(row_index, column) else "" for column in range(self.grid.columnCount())])
            result = QueryResult(sql=self.editor.toPlainText(), columns=columns, rows=[tuple(row) for row in rows])
            try:
                result.save_csv(path)
                self.statusMessage.emit(f"Сохранено: {path}")
            except OSError as exc:
                self.statusMessage.emit(f"Не удалось сохранить CSV: {exc}")

else:

    class SqlConsoleWidget:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PySide6 is required for the SQL console")
