"""Command snippets panel — quick-send saved commands to the terminal."""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QInputDialog,
)
from PyQt6.QtCore import pyqtSignal, Qt

_LINUX = sys.platform.startswith("linux")


class SnippetsPanel(QWidget):
    """
    Saved command launcher.

    Double-click a snippet or press ⚡ Send to emit send_command(str),
    which the parent TerminalWidget forwards to the SSH channel.

    Snippets are stored in the DB.  conn_id=None means global (visible
    in every session); conn_id=<id> means tied to one connection.
    """

    send_command = pyqtSignal(str)

    def __init__(self, db=None, conn_id: int | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db
        self._conn_id = conn_id
        self._build_ui()
        self._reload()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Header row
        hdr = QHBoxLayout()
        lbl = QLabel("<b>Commands</b>")
        lbl.setStyleSheet("color: #ccc;")
        hdr.addWidget(lbl)
        hdr.addStretch()

        self._btn_add = QPushButton("+")
        self._btn_add.setFixedSize(24, 24)
        self._btn_add.setToolTip("Add snippet")
        self._btn_add.setEnabled(self._db is not None)
        self._btn_add.clicked.connect(self._on_add)
        hdr.addWidget(self._btn_add)

        self._btn_del = QPushButton("−")
        self._btn_del.setFixedSize(24, 24)
        self._btn_del.setToolTip("Delete selected")
        self._btn_del.setEnabled(False)
        self._btn_del.clicked.connect(self._on_delete)
        hdr.addWidget(self._btn_del)

        layout.addLayout(hdr)

        # Snippet list
        self._list = QListWidget()
        self._list.setStyleSheet(
            "QListWidget { background: #252526; color: #ccc; border: none; }"
            "QListWidget::item:selected { background: #094771; }"
            "QListWidget::item:hover { background: #2a2d2e; }"
        )
        self._list.setToolTip("Double-click to send")
        self._list.itemDoubleClicked.connect(self._on_send_item)
        self._list.currentItemChanged.connect(
            lambda cur, _: self._btn_del.setEnabled(
                cur is not None and self._db is not None
            )
        )
        layout.addWidget(self._list)

        # Send button
        btn_send = QPushButton("Send" if _LINUX else "⚡  Send")
        btn_send.setStyleSheet(
            "QPushButton { background: #2563eb; color: white; border-radius: 4px;"
            " border: none; padding: 4px; }"
            "QPushButton:hover { background: #1d4ed8; }"
            "QPushButton:disabled { background: #333; color: #666; }"
        )
        btn_send.clicked.connect(self._on_send_selected)
        layout.addWidget(btn_send)

        if self._db is None:
            info = QLabel("Save the connection to enable snippets.")
            info.setStyleSheet("color: #666; font-size: 11px;")
            info.setWordWrap(True)
            layout.addWidget(info)

    # ── Data ─────────────────────────────────────────────────────────────────

    def _reload(self) -> None:
        self._list.clear()
        if self._db is None:
            return
        for s in self._db.all_snippets(self._conn_id):
            item = QListWidgetItem(s["title"])
            item.setData(Qt.ItemDataRole.UserRole, s["command"])
            item.setData(Qt.ItemDataRole.UserRole + 1, s["id"])
            item.setToolTip(s["command"])
            self._list.addItem(item)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _on_send_item(self, item: QListWidgetItem) -> None:
        cmd = item.data(Qt.ItemDataRole.UserRole)
        if cmd is not None:
            self.send_command.emit(cmd + "\n")

    def _on_send_selected(self) -> None:
        item = self._list.currentItem()
        if item:
            self._on_send_item(item)

    def _on_add(self) -> None:
        title, ok = QInputDialog.getText(self, "Add Command", "Label:")
        if not ok or not title.strip():
            return
        cmd, ok = QInputDialog.getMultiLineText(
            self, "Add Command", f"Command for «{title.strip()}»:"
        )
        if not ok:
            return
        scope = "connection" if self._conn_id else "global"
        choice, ok = QInputDialog.getItem(
            self, "Scope", "Make this snippet:",
            ["Global (all sessions)", "This connection only"],
            0, False,
        )
        if not ok:
            return
        cid = self._conn_id if "connection" in choice.lower() else None
        self._db.save_snippet(title.strip(), cmd.strip(), cid)
        self._reload()

    def _on_delete(self) -> None:
        item = self._list.currentItem()
        if not item or not self._db:
            return
        sid = item.data(Qt.ItemDataRole.UserRole + 1)
        if sid is not None:
            self._db.delete_snippet(sid)
            self._reload()
