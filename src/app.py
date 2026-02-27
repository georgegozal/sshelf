"""QApplication subclass — sets up global style and shared resources."""

from __future__ import annotations

import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont, QPalette, QColor
from PyQt6.QtCore import Qt


class Application(QApplication):
    """RemminaMac application."""

    APP_NAME = "RemminaMac"
    APP_VERSION = "0.1.0"
    ORG_NAME = "RemminaMac"

    def __init__(self, argv: list[str]) -> None:
        super().__init__(argv)

        self.setApplicationName(self.APP_NAME)
        self.setApplicationVersion(self.APP_VERSION)
        self.setOrganizationName(self.ORG_NAME)

        # Use the system font at a comfortable size
        font = self.font()
        font.setPointSize(13)
        self.setFont(font)

        self._launch_main_window()

    def _launch_main_window(self) -> None:
        from src.ui.main_window import MainWindow
        from src.storage.database import Database

        self._db = Database()
        self._main_window = MainWindow(self._db)
        self._main_window.show()

        # Clean up DB on exit
        self.aboutToQuit.connect(self._db.close)
