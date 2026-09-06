"""A small ANSI-friendly terminal surface for the desktop shell."""

from __future__ import annotations

from typing import Callable

try:  # Qt is optional for core-only deployments.
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtGui import QTextCursor
    from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QTextEdit, QVBoxLayout, QWidget
except ImportError:  # pragma: no cover - exercised only when optional Qt is absent.
    QT_AVAILABLE = False
else:
    QT_AVAILABLE = True


if QT_AVAILABLE:

    class TerminalWidget(QWidget):
        commandExecuted = Signal(str)

        def __init__(self, host: str, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.host = host
            self._command_handler: Callable[[str], str] | None = None
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            self.output = QTextEdit(objectName="terminalOutput", readOnly=True)
            self.output.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
            self.output.setPlainText(
                f"Cashdesk Control SSH gateway · OpenSSH_8.9p1\n"
                f"Подключение к {host} через защищённый канал\n\n"
                f"alexey@cashdesk-01:~$ systemctl status cashdesk --no-pager\n"
                "● cashdesk.service — CashDesk POS service\n"
                "     Active: active (running)\n\n"
                "alexey@cashdesk-01:~$ "
            )
            layout.addWidget(self.output, 1)

            input_row = QHBoxLayout()
            input_row.setContentsMargins(12, 8, 12, 10)
            input_row.setSpacing(5)
            prompt = QLineEdit(readOnly=True)
            prompt.setText("alexey@cashdesk-01:~$ ")
            prompt.setFixedWidth(153)
            prompt.setStyleSheet("QLineEdit { border: 0; background: transparent; color: #55d6a2; padding: 0; }")
            self.input = QLineEdit(placeholderText="Введите команду…")
            self.input.returnPressed.connect(self.execute_command)
            submit = QPushButton("↵")
            submit.setFixedWidth(30)
            submit.clicked.connect(self.execute_command)
            input_row.addWidget(prompt)
            input_row.addWidget(self.input, 1)
            input_row.addWidget(submit)
            layout.addLayout(input_row)

        def set_command_handler(self, handler: Callable[[str], str]) -> None:
            self._command_handler = handler

        def execute_command(self) -> None:
            command = self.input.text().strip()
            if not command:
                return
            cursor = self.output.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertText(f"{command}\n")
            response = self._command_handler(command) if self._command_handler else "Команда выполнена."
            cursor.insertText(f"{response}\nalexey@cashdesk-01:~$ ")
            self.output.setTextCursor(cursor)
            self.output.ensureCursorVisible()
            self.input.clear()
            self.commandExecuted.emit(command)

        def clear(self) -> None:
            self.output.clear()
            self.output.setPlainText("alexey@cashdesk-01:~$ ")

else:

    class TerminalWidget:  # type: ignore[no-redef]
        """Import-safe placeholder when PySide6 is not installed."""

        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PySide6 is required for the desktop terminal widget")
