"""Two-pane file manager: workstation disk on the left, cashier over SFTP on the right."""

from __future__ import annotations

import logging
from typing import Any

from ...core.asyncio_utils import schedule
from ...core.files import EntryInfo, FileSystem, LocalFileSystem, is_text_file, join, parent_of

try:
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtGui import QStandardItem, QStandardItemModel
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QDialog,
        QDialogButtonBox,
        QFileDialog,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLineEdit,
        QMessageBox,
        QPlainTextEdit,
        QPushButton,
        QSplitter,
        QTreeView,
        QVBoxLayout,
        QWidget,
    )
except ImportError:  # pragma: no cover
    QT_AVAILABLE = False
else:
    QT_AVAILABLE = True

logger = logging.getLogger("cashdesk_control.files")

_COLUMNS = ("Имя", "Размер", "Изменён", "Права")


if QT_AVAILABLE:

    class FilePane(QWidget):
        """One side of the manager."""

        pathActivated = Signal(str)
        fileActivated = Signal(str)
        statusMessage = Signal(str)

        def __init__(self, title: str, kind: str, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.title = title
            self.kind = kind
            self.fs: FileSystem | None = None
            self.current_path = "/" if kind != "local" else ("/" if __import__("os").name != "nt" else "C:\\")
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(6)

            header = QHBoxLayout()
            header.setSpacing(6)
            self.label = QLabel(title, objectName="sectionTitle")
            header.addWidget(self.label)
            header.addStretch()
            self.badge = QLabel("не подключено", objectName="dim")
            header.addWidget(self.badge)
            layout.addLayout(header)

            nav = QHBoxLayout()
            nav.setSpacing(5)
            up = QPushButton("↑", objectName="secondary")
            up.setToolTip("На уровень выше")
            up.clicked.connect(self.go_up)
            nav.addWidget(up)
            self.path_edit = QLineEdit()
            self.path_edit.setText(self.current_path)
            self.path_edit.returnPressed.connect(lambda: schedule(self.open_path(self.path_edit.text())))
            nav.addWidget(self.path_edit, 1)
            go = QPushButton("Перейти", objectName="secondary")
            go.clicked.connect(lambda: schedule(self.open_path(self.path_edit.text())))
            nav.addWidget(go)
            refresh = QPushButton("↻", objectName="secondary")
            refresh.clicked.connect(self.refresh)
            nav.addWidget(refresh)
            layout.addLayout(nav)

            self.model = QStandardItemModel(0, len(_COLUMNS))
            self.model.setHorizontalHeaderLabels(list(_COLUMNS))
            self.view = QTreeView()
            self.view.setModel(self.model)
            self.view.setRootIsDecorated(False)
            self.view.setAlternatingRowColors(True)
            self.view.setSortingEnabled(True)
            self.view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            self.view.doubleClicked.connect(self._double_clicked)
            header_view = self.view.header()
            header_view.setStretchLastSection(True)
            header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            for index in range(1, len(_COLUMNS)):
                header_view.setSectionResizeMode(index, QHeaderView.ResizeMode.ResizeToContents)
            layout.addWidget(self.view, 1)

        # -- backend ------------------------------------------------------------
        def attach(self, fs: FileSystem, start_path: str | None = None) -> None:
            self.fs = fs
            self.badge.setText("локальный диск" if fs.kind == "local" else "SFTP")
            if start_path:
                self.current_path = start_path
            self.path_edit.setText(self.current_path)
            self.refresh()

        def detach(self) -> None:
            self.fs = None
            self.badge.setText("не подключено")
            self.model.removeRows(0, self.model.rowCount())

        def refresh(self) -> None:
            schedule(self.open_path(self.current_path))

        async def open_path(self, path: str) -> None:
            if self.fs is None:
                return
            try:
                entries = await self.fs.listdir(path)
            except Exception as exc:
                self.statusMessage.emit(f"{self.title}: {exc}")
                self.badge.setText("ошибка чтения")
                return
            self.current_path = path
            self.path_edit.setText(path)
            self._render(entries)
            self.statusMessage.emit(f"{self.title}: {len(entries)} элементов в {path}")

        def _render(self, entries: list[EntryInfo]) -> None:
            self.model.removeRows(0, self.model.rowCount())
            for entry in entries:
                icon = "🗀 " if entry.is_dir else ("🗎 " if is_text_file(entry.name) else "· ")
                name = QStandardItem(f"{icon}{entry.name}")
                name.setData(entry.path, Qt.ItemDataRole.UserRole)
                name.setData(entry.is_dir, Qt.ItemDataRole.UserRole + 1)
                row = [
                    name,
                    QStandardItem(entry.display_size),
                    QStandardItem(entry.display_modified),
                    QStandardItem(entry.permissions),
                ]
                for item in row:
                    item.setEditable(False)
                self.model.appendRow(row)

        def selected_entry(self) -> tuple[str, bool] | None:
            indexes = self.view.selectionModel().selectedRows()
            if not indexes:
                return None
            row = indexes[0].row()
            path = self.model.item(row, 0).data(Qt.ItemDataRole.UserRole)
            is_dir = bool(self.model.item(row, 0).data(Qt.ItemDataRole.UserRole + 1))
            return str(path), is_dir

        def go_up(self) -> None:
            schedule(self.open_path(parent_of(self.current_path, self.fs.kind if self.fs else "posix")))

        def _double_clicked(self, index) -> None:
            row = index.row()
            path = str(self.model.item(row, 0).data(Qt.ItemDataRole.UserRole))
            is_dir = bool(self.model.item(row, 0).data(Qt.ItemDataRole.UserRole + 1))
            if is_dir:
                schedule(self.open_path(path))
                self.pathActivated.emit(path)
            else:
                self.fileActivated.emit(path)

    class FileEditorDialog(QDialog):
        """Small editor used for both local and remote text files."""

        def __init__(self, path: str, content: str, remote: bool, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setWindowTitle(f"Редактор — {path}")
            self.resize(880, 620)
            self.saved = False
            layout = QVBoxLayout(self)
            hint = QLabel("Файл кассы: сохранение запишет его обратно по SFTP." if remote else "Локальный файл.", objectName="dim")
            layout.addWidget(hint)
            self.editor = QPlainTextEdit()
            self.editor.setObjectName("sqlEditor")
            self.editor.setPlainText(content)
            layout.addWidget(self.editor, 1)
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Close)
            buttons.button(QDialogButtonBox.StandardButton.Save).setText("Сохранить")
            buttons.button(QDialogButtonBox.StandardButton.Close).setText("Закрыть")
            buttons.accepted.connect(self._save)
            buttons.rejected.connect(self.reject)
            layout.addWidget(buttons)

        def _save(self) -> None:
            self.saved = True
            self.accept()

        def text(self) -> str:
            return self.editor.toPlainText()

    class FileManagerWidget(QWidget):
        """The files tab: two panes plus copy/upload/download actions."""

        statusMessage = Signal(str)

        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self._remote_fs: FileSystem | None = None
            layout = QVBoxLayout(self)
            layout.setContentsMargins(12, 12, 12, 12)
            layout.setSpacing(8)

            splitter = QSplitter(Qt.Orientation.Horizontal)
            self.local = FilePane("Локальный диск", "local")
            self.remote = FilePane("Касса (SFTP)", "sftp")
            for pane in (self.local, self.remote):
                pane.statusMessage.connect(self.statusMessage.emit)
                pane.fileActivated.connect(lambda path, source=pane: self.edit_file(source, path))
            splitter.addWidget(self.local)
            splitter.addWidget(self.remote)
            splitter.setSizes([480, 520])
            layout.addWidget(splitter, 1)

            self.local.attach(LocalFileSystem())

            actions = QHBoxLayout()
            actions.setSpacing(6)
            for label, slot in (
                ("Загрузить на кассу →", self.upload_selected),
                ("← Скачать с кассы", self.download_selected),
                ("Копировать путь", self.copy_path),
                ("Удалить на кассе", self.delete_remote),
            ):
                button = QPushButton(label, objectName="secondary")
                button.clicked.connect(slot)
                actions.addWidget(button)
            actions.addStretch()
            layout.addLayout(actions)

        def attach_remote(self, fs: FileSystem, home: str = "/home/tc") -> None:
            self._remote_fs = fs
            self.remote.attach(fs, home)

        def detach_remote(self) -> None:
            self._remote_fs = None
            self.remote.detach()

        # -- actions -------------------------------------------------------------
        def copy_path(self) -> None:
            from PySide6.QtWidgets import QApplication

            for pane in (self.remote, self.local):
                selection = pane.selected_entry()
                if selection:
                    QApplication.clipboard().setText(selection[0])
                    self.statusMessage.emit(f"Скопировано: {selection[0]}")
                    return
            self.statusMessage.emit("Выберите файл или каталог")

        def upload_selected(self) -> None:
            selection = self.local.selected_entry()
            if not selection or self._remote_fs is None:
                self.statusMessage.emit("Выберите локальный файл и подключитесь к кассе")
                return
            source, _ = selection
            target = join(self.remote.current_path, source.rsplit("/", 1)[-1].replace("\\", "/").split("/")[-1])
            self.statusMessage.emit(f"Загрузка {source} → {target}")
            schedule(self._transfer(source, target, upload=True))

        def download_selected(self) -> None:
            selection = self.remote.selected_entry()
            if not selection:
                self.statusMessage.emit("Выберите файл на кассе")
                return
            source, is_dir = selection
            if is_dir:
                self.statusMessage.emit("Каталоги скачиваются архивом — выберите файл")
                return
            target, _ = QFileDialog.getSaveFileName(self, "Сохранить файл", source.rsplit("/", 1)[-1])
            if not target:
                return
            self.statusMessage.emit(f"Скачивание {source} → {target}")
            schedule(self._transfer(source, target, upload=False))

        async def _transfer(self, source: str, target: str, *, upload: bool) -> None:
            try:
                if upload:
                    await self._remote_fs.upload(source, target)  # type: ignore[union-attr]
                else:
                    await self._remote_fs.download(source, target)  # type: ignore[union-attr]
                self.statusMessage.emit("Готово")
                self.remote.refresh()
                self.local.refresh()
            except Exception as exc:
                self.statusMessage.emit(f"Ошибка передачи: {exc}")

        def delete_remote(self) -> None:
            selection = self.remote.selected_entry()
            if not selection or self._remote_fs is None:
                self.statusMessage.emit("Выберите элемент на кассе")
                return
            path, is_dir = selection
            answer = QMessageBox.question(
                self,
                "Удаление на кассе",
                f"Удалить {path}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer is not QMessageBox.StandardButton.Yes:
                return
            schedule(self._delete(path, is_dir))

        async def _delete(self, path: str, is_dir: bool) -> None:
            try:
                await self._remote_fs.remove(path, recursive=is_dir)  # type: ignore[union-attr]
                self.statusMessage.emit(f"Удалено: {path}")
                self.remote.refresh()
            except Exception as exc:
                self.statusMessage.emit(f"Не удалось удалить: {exc}")

        def edit_file(self, pane: FilePane, path: str) -> None:
            schedule(self._edit_async(pane, path))

        async def _edit_async(self, pane: FilePane, path: str) -> None:
            if pane.fs is None or not is_text_file(path.rsplit("/", 1)[-1]):
                self.statusMessage.emit("Файл не похож на текстовый")
                return
            try:
                data = await pane.fs.read_bytes(path, 1_500_000)
            except Exception as exc:
                self.statusMessage.emit(f"Не удалось открыть: {exc}")
                return
            dialog = FileEditorDialog(path, data.decode("utf-8", "replace"), pane.fs.kind != "local", self)
            dialog.exec()
            if not dialog.saved:
                return
            try:
                await pane.fs.write_bytes(path, dialog.text().encode("utf-8"))
                self.statusMessage.emit(f"Сохранено: {path}")
            except Exception as exc:
                self.statusMessage.emit(f"Не удалось сохранить: {exc}")

else:

    class FileManagerWidget:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PySide6 is required for the file manager")
