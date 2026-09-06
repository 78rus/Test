from __future__ import annotations

import unittest

from cashdesk_control.ui import MainWindow, QT_AVAILABLE


class OptionalUiTests(unittest.TestCase):
    def test_ui_module_is_safe_to_import_without_qt(self) -> None:
        if QT_AVAILABLE:
            self.skipTest("PySide6 is installed in this environment")
        with self.assertRaisesRegex(RuntimeError, "PySide6"):
            MainWindow()


if __name__ == "__main__":
    unittest.main()
