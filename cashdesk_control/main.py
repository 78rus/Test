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
        message = "PySide6 is not installed. Install the desktop extras with: pip install -e '.[qt,ssh]'"
        logger.error(message)
        print(message)
        return 2

    # qasync runs asyncio inside the Qt event loop, which is what keeps SSH,
    # SFTP, VNC and SQL off the GUI thread. Without it the window would open but
    # could not connect to anything, so refuse to start in a half-working state.
    try:
        from qasync import QEventLoop
    except ImportError:
        message = (
            "qasync is not installed, so SSH/VNC/SQL would not work. "
            "Install the desktop extras with: pip install -e '.[qt,ssh]'"
        )
        logger.error(message)
        print(message)
        return 2

    app = QApplication(sys.argv)
    app.setApplicationName("Касса Control")
    app.setOrganizationName("Cashdesk Control")
    app.setStyle("Fusion")

    # The loop must exist before the window is built: widgets schedule
    # background work (listing the local directory, restoring profiles) while
    # they are being constructed.
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    from .ui.main_window import MainWindow

    window = MainWindow()
    window.show()
    logger.info("desktop application started")

    with loop:
        loop.run_forever()
    logger.info("desktop application stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
