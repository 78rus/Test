"""Desktop application entry point."""

from __future__ import annotations

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
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
