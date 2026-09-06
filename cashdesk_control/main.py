"""Desktop application entry point."""

from __future__ import annotations

import asyncio
import sys


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("PySide6 is not installed. Install the desktop extras with: pip install -e '.[qt]'")
        return 2

    from .ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Касса Control")
    app.setOrganizationName("Cashdesk Control")
    window = MainWindow()
    window.show()

    # qasync lets Qt slots schedule AsyncSSH/SFTP tasks without blocking the
    # GUI. A plain Qt loop remains a useful fallback for the demo transport.
    try:
        from qasync import QEventLoop
    except ImportError:
        return app.exec()

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    with loop:
        loop.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
