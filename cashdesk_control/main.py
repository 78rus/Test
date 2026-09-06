"""Desktop application entry point."""

from __future__ import annotations

import asyncio
import sys

from .core.logger import configure_logging


def main() -> int:
    logger = configure_logging()
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        message = "PySide6 is not installed. Install the desktop extras with: pip install -e '.[qt]'"
        logger.error(message)
        print(message)
        return 2

    from .ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Касса Control")
    app.setOrganizationName("Cashdesk Control")
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    logger.info("desktop application started")

    # qasync lets Qt slots schedule AsyncSSH/SFTP tasks without blocking the
    # GUI. A plain Qt loop remains a useful fallback for the demo transport.
    try:
        from qasync import QEventLoop
    except ImportError:
        logger.warning("qasync is not installed; using the plain Qt event loop")
        return app.exec()

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    with loop:
        loop.run_forever()
    logger.info("desktop application stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
