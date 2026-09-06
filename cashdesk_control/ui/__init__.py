"""PySide6 presentation layer.

The module is optional: importing the package remains safe on a headless machine
without Qt, which is useful for the core test suite and CI.
"""

from .main_window import QT_AVAILABLE, MainWindow

__all__ = ["MainWindow", "QT_AVAILABLE"]
