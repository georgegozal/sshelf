"""App preferences dialog."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QDialogButtonBox,
    QSpinBox, QCheckBox, QLabel, QComboBox,
)
from PyQt6.QtCore import Qt

from src.storage.database import Database


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
        self.accept()
