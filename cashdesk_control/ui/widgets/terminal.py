"""A small ANSI-friendly terminal surface for the desktop shell."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

try:  # Qt is optional for core-only deployments.
    from PySide6.QtCore import Signal
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
            self._async_command_handler: Callable[[str], Awaitable[str]] | None = None
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            self.output = QTextEdit()
            self.output.setObjectName("terminalOutput")
            self.output.setReadOnly(True)
            self.output.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
            self.output.setPlainText(
                "Cashdesk Control SSH gateway · OpenSSH_8.9p1\n"
                f"Подключение к {host} через защищённый канал\n\n"
                "alexey@cashdesk-01:~$ systemctl status cashdesk --no-pager\n"
                "● cashdesk.service — CashDesk POS service\n"
                "     Active: active (running)\n\n"
                "alexey@cashdesk-01:~$ "
            )
            layout.addWidget(self.output, 1)

            input_row = QHBoxLayout()
            input_row.setContentsMargins(12, 8, 12, 10)
            input_row.setSpacing(5)
            prompt = QLineEdit()
            prompt.setReadOnly(True)
            prompt.setText("alexey@cashdesk-01:~$ ")
            prompt.setFixedWidth(153)
            prompt.setStyleSheet("QLineEdit { border: 0; background: transparent; color: #55d6a2; padding: 0; }")
            self.input = QLineEdit()
            self.input.setPlaceholderText("Введите команду…")
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
            self._async_command_handler = None

        def set_async_command_handler(self, handler: Callable[[str], Awaitable[str]]) -> None:
            self._async_command_handler = handler
            self._command_handler = None

        def execute_command(self) -> None:
            command = self.input.text().strip()
            if not command:
                return
            self._append_text(f"{command}\n")
            self.input.clear()
            self.commandExecuted.emit(command)
            if self._async_command_handler is not None:
                self.input.setEnabled(False)
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    asyncio.run(self._execute_async(command))
                else:
                    loop.create_task(self._execute_async(command))
                return
            response = self._command_handler(command) if self._command_handler else "Команда выполнена."
            self._append_text(f"{response}\nalexey@cashdesk-01:~$ ")

        async def _execute_async(self, command: str) -> None:
            try:
                response = await self._async_command_handler(command)  # type: ignore[misc]
            except Exception as exc:  # Surface remote errors in the terminal, not as GUI crashes.
                response = f"ssh: {exc}"
            self._append_text(f"{response}\nalexey@cashdesk-01:~$ ")
            self.input.setEnabled(True)
            self.input.setFocus()

        def _append_text(self, text: str) -> None:
            cursor = self.output.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertText(text)
            self.output.setTextCursor(cursor)
            self.output.ensureCursorVisible()

        def clear(self) -> None:
            self.output.clear()
            self.output.setPlainText("alexey@cashdesk-01:~$ ")

else:

    class TerminalWidget:  # type: ignore[no-redef]
        """Import-safe placeholder when PySide6 is not installed."""

        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PySide6 is required for the desktop terminal widget")
