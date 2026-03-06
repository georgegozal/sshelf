"""App preferences dialog."""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QDialogButtonBox,
    QSpinBox, QCheckBox, QLabel, QComboBox,
)
from PyQt6.QtCore import Qt

from src.storage.database import Database
from src.app import Application

_LINUX = sys.platform.startswith("linux")

_SYSTEM_DEFAULT = "(system default)"


def _list_icon_themes() -> list[str]:
    """
    Return sorted names of icon themes installed on this Linux system.

    Searches the standard XDG icon directories and returns directory names
    that contain an ``index.theme`` file.  Always starts with the
    ``_SYSTEM_DEFAULT`` sentinel so the user can revert to the DE choice.
    """
    search_dirs = [
        Path.home() / ".icons",
        Path.home() / ".local" / "share" / "icons",
        Path("/usr/share/icons"),
        Path("/usr/local/share/icons"),
    ]
    seen: set[str] = set()
    for d in search_dirs:
        try:
            for entry in d.iterdir():
                if (
                    entry.is_dir()
                    and (entry / "index.theme").exists()
                    and not entry.name.startswith(".")
                    # skip cursor-only themes (they rarely contain app icons)
                    and not entry.name.lower().endswith("-cursor")
                    and entry.name.lower() != "default"
                ):
                    seen.add(entry.name)
        except OSError:
            pass
    return [_SYSTEM_DEFAULT] + sorted(seen, key=str.casefold)


class PreferencesDialog(QDialog):
    """Simple preferences dialog backed by DB key/value store."""

    def __init__(self, db: Database, parent=None) -> None:
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Preferences")
        self.setMinimumWidth(380)
        self.setModal(True)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(10)
        form.setContentsMargins(16, 16, 16, 16)

        self._font_size = QSpinBox()
        self._font_size.setRange(8, 24)
        self._font_size.setValue(int(db.get_pref("terminal_font_size", "13")))
        form.addRow("Terminal font size:", self._font_size)

        self._keep_alive = QSpinBox()
        self._keep_alive.setRange(0, 3600)
        self._keep_alive.setSuffix(" s")
        self._keep_alive.setValue(int(db.get_pref("default_keep_alive", "60")))
        self._keep_alive.setToolTip("Default keep-alive for new connections (0 = off)")
        form.addRow("Default keep-alive:", self._keep_alive)

        self._confirm_delete = QCheckBox()
        self._confirm_delete.setChecked(db.get_pref("confirm_delete", "1") == "1")
        form.addRow("Confirm before delete:", self._confirm_delete)

        self._theme = QComboBox()
        self._theme.addItems(["System", "Light", "Dark"])
        saved = db.get_pref("app_theme", "system")
        self._theme.setCurrentIndex({"system": 0, "light": 1, "dark": 2}.get(saved, 0))
        form.addRow("App theme:", self._theme)

        from src.ui.themes import theme_names
        self._terminal_theme = QComboBox()
        self._terminal_theme.addItems(theme_names())
        saved_tt = db.get_pref("terminal_theme", theme_names()[0])
        idx = self._terminal_theme.findText(saved_tt)
        self._terminal_theme.setCurrentIndex(max(0, idx))
        form.addRow("Terminal theme:", self._terminal_theme)

        # Icon theme — Linux / freedesktop only
        self._icon_theme: QComboBox | None = None
        if _LINUX:
            self._icon_theme = QComboBox()
            themes = _list_icon_themes()
            self._icon_theme.addItems(themes)
            saved_it = db.get_pref("icon_theme", "")
            it_label = saved_it if saved_it else _SYSTEM_DEFAULT
            it_idx = self._icon_theme.findText(it_label)
            self._icon_theme.setCurrentIndex(max(0, it_idx))
            self._icon_theme.setToolTip(
                "Freedesktop icon theme used for toolbar and panel icons.\n"
                "Popular choices: Papirus, Adwaita, Tango, Breeze, Numix."
            )
            form.addRow("Icon theme:", self._icon_theme)

        layout.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _save(self) -> None:
        self.db.set_pref("terminal_font_size", str(self._font_size.value()))
        self.db.set_pref("default_keep_alive", str(self._keep_alive.value()))
        self.db.set_pref("confirm_delete", "1" if self._confirm_delete.isChecked() else "0")
        theme = ["system", "light", "dark"][self._theme.currentIndex()]
        self.db.set_pref("app_theme", theme)
        Application.apply_theme(theme)
        terminal_theme_name = self._terminal_theme.currentText()
        self.db.set_pref("terminal_theme", terminal_theme_name)

        # Apply icon theme immediately (Linux only)
        if _LINUX and self._icon_theme is not None:
            chosen = self._icon_theme.currentText()
            it_name = "" if chosen == _SYSTEM_DEFAULT else chosen
            self.db.set_pref("icon_theme", it_name)
            Application.apply_icon_theme(it_name)

        self.accept()
