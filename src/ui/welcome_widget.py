"""Welcome screen and connection detail panel."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
)
from PyQt6.QtCore import Qt

from src.models.connection import Connection


class WelcomeWidget(QWidget):
    """Shown when no connection is selected."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon = QLabel("🖥️")
        icon.setStyleSheet("font-size: 64px;")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("RemminaMac")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel(
            "Single-click a connection to view details and connect,\n"
            "or double-click to open a terminal directly.\n\n"
            "Use ＋ New in the toolbar to add your first server."
        )
        subtitle.setStyleSheet("color: palette(mid); font-size: 14px;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        for w in (icon, title, subtitle):
            layout.addWidget(w)


class DetailWidget(QWidget):
    """Shows key properties of a selected connection with a Connect button."""

    def __init__(self, conn: Connection, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)

        # Title row
        title_row = QHBoxLayout()
        icon = QLabel("🔑")
        icon.setStyleSheet("font-size: 36px;")
        title_row.addWidget(icon)

        name_lbl = QLabel(self._conn.display_name())
        name_lbl.setStyleSheet("font-size: 22px; font-weight: bold;")
        title_row.addWidget(name_lbl)
        title_row.addStretch()
        layout.addLayout(title_row)

        # Details card
        card = QFrame()
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card.setStyleSheet("QFrame { border-radius: 8px; padding: 8px; }")
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(6)

        def row(label: str, value: str) -> None:
            if not value:
                return
            hl = QHBoxLayout()
            lbl = QLabel(f"<b>{label}</b>")
            lbl.setFixedWidth(130)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            val = QLabel(value)
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            hl.addWidget(lbl)
            hl.addWidget(val)
            hl.addStretch()
            card_layout.addLayout(hl)

        c = self._conn
        row("Host:", c.host)
        row("Port:", str(c.port))
        row("Username:", c.username or "(none specified)")
        row("Group:", c.group)
        row("Auth:", c.auth_method())
        row("Jump Host:", c.jump_host)
        row("Startup Cmd:", c.startup_command)
        if c.notes:
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            card_layout.addWidget(sep)
            notes = QLabel(c.notes)
            notes.setWordWrap(True)
            notes.setStyleSheet("color: palette(mid);")
            card_layout.addWidget(notes)

        layout.addWidget(card)

        # Connect button — full width, prominent
        btn = QPushButton("⚡   Connect")
        btn.setFixedHeight(48)
        btn.setStyleSheet(
            "QPushButton { font-size: 16px; font-weight: bold;"
            " background: #2563eb; color: white;"
            " border-radius: 8px; border: none; }"
            "QPushButton:hover { background: #1d4ed8; }"
            "QPushButton:pressed { background: #1e40af; }"
        )
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self._on_connect)
        layout.addStretch()
        layout.addWidget(btn)

    def _on_connect(self) -> None:
        win = self.window()
        if hasattr(win, "_on_connection_activated"):
            win._on_connection_activated(self._conn)
