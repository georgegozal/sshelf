"""QApplication subclass — sets up global style and shared resources."""

from __future__ import annotations

import sys
from PyQt6.QtWidgets import QApplication, QStyleFactory
from PyQt6.QtGui import QFont, QPalette, QColor, QIcon
from PyQt6.QtCore import Qt

_LINUX = sys.platform.startswith("linux")


class Application(QApplication):
    """sshelf application."""

    APP_NAME = "SSHelf"
    APP_VERSION = "0.1.0"
    ORG_NAME = "sshelf"

    def __init__(self, argv: list[str], name: str | None = None) -> None:
        super().__init__(argv)

        self.setApplicationName(self.APP_NAME)
        self.setApplicationVersion(self.APP_VERSION)
        self.setOrganizationName(self.ORG_NAME)

        # Use the system font at a comfortable size
        font = self.font()
        font.setPointSize(13)
        self.setFont(font)

        self._launch_main_window(name=name)

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    @staticmethod
    def apply_icon_theme(name: str) -> None:
        """
        Switch the freedesktop icon theme (Linux only).

        *name* is a theme directory name such as "Papirus", "Adwaita", or
        "hicolor".  Pass an empty string to keep whatever the desktop
        environment chose automatically.
        """
        if not _LINUX:
            return
        if name:
            QIcon.setThemeName(name)

    @staticmethod
    def apply_theme(theme: str) -> None:
        """Apply 'dark', 'light', or 'system' theme to the running app."""
        app = QApplication.instance()

        if theme == "dark":
            app.setStyle("Fusion")
            p = QPalette()
            p.setColor(QPalette.ColorRole.Window,          QColor(45, 45, 45))
            p.setColor(QPalette.ColorRole.WindowText,      QColor(220, 220, 220))
            p.setColor(QPalette.ColorRole.Base,            QColor(30, 30, 30))
            p.setColor(QPalette.ColorRole.AlternateBase,   QColor(40, 40, 40))
            p.setColor(QPalette.ColorRole.Text,            QColor(220, 220, 220))
            p.setColor(QPalette.ColorRole.Button,          QColor(55, 55, 55))
            p.setColor(QPalette.ColorRole.ButtonText,      QColor(220, 220, 220))
            p.setColor(QPalette.ColorRole.Highlight,       QColor(42, 130, 218))
            p.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
            p.setColor(QPalette.ColorRole.Link,            QColor(42, 130, 218))
            p.setColor(QPalette.ColorRole.BrightText,      QColor(255, 255, 255))
            p.setColor(QPalette.ColorRole.ToolTipBase,     QColor(55, 55, 55))
            p.setColor(QPalette.ColorRole.ToolTipText,     QColor(220, 220, 220))
            for role in (QPalette.ColorRole.WindowText,
                         QPalette.ColorRole.Text,
                         QPalette.ColorRole.ButtonText):
                p.setColor(QPalette.ColorGroup.Disabled, role, QColor(128, 128, 128))
            app.setPalette(p)

        elif theme == "light":
            app.setStyle("Fusion")
            app.setPalette(QPalette())

        else:  # "system"
            available = [k.lower() for k in QStyleFactory.keys()]
            if "macos" in available:
                app.setStyle("macOS")
            app.setPalette(QPalette())

    def _launch_main_window(self, name: str | None = None) -> None:
        from src.ui.main_window import MainWindow
        from src.storage.database import Database

        self._db = Database()
        self.apply_theme(self._db.get_pref("app_theme", "system"))
        # Apply saved icon theme BEFORE building the main window so all
        # QIcon.fromTheme() calls pick it up from the start.
        self.apply_icon_theme(self._db.get_pref("icon_theme", ""))
        self._main_window = MainWindow(self._db, name=name)
        self._main_window.show()

        # Clean up DB on exit
        self.aboutToQuit.connect(self._db.close)
