"""Dialog for importing connections from ~/.ssh/config."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QMessageBox, QFileDialog,
)

from src.models.connection import Connection
from src.storage.database import Database


def _parse_ssh_config(path: Path) -> list[dict]:
    """
    Parse an OpenSSH config file into a list of host dicts.
    Skips the catch-all 'Host *' entry.
    """
    hosts: list[dict] = []
    current: Optional[dict] = None

    for raw in path.read_text(errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        m = re.match(r"^(\w+)\s+(.+)$", line)
        if not m:
            continue
        key, value = m.group(1).lower(), m.group(2).strip()

        if key == "host":
            # Each pattern in the Host line is a separate alias; skip wildcards
            aliases = [a for a in value.split() if "*" not in a and "?" not in a]
            if not aliases:
                current = None
                continue
            # Use the first alias as the connection name
            current = {"name": aliases[0], "alias": aliases[0]}
            hosts.append(current)
        elif current is not None:
            if key == "hostname":
                current["hostname"] = value
            elif key == "user":
                current["user"] = value
            elif key == "port":
                try:
                    current["port"] = int(value)
                except ValueError:
                    pass
            elif key == "identityfile":
                current["identityfile"] = str(Path(value).expanduser())
            elif key in ("proxyjump", "proxyjump"):
                current["proxyjump"] = value

    return hosts


def _host_to_connection(h: dict) -> Connection:
    conn = Connection()
    conn.name     = h.get("name", "")
    conn.host     = h.get("hostname", h.get("alias", ""))
    conn.username = h.get("user", "")
    conn.port     = h.get("port", 22)
    conn.private_key_file = h.get("identityfile", "")
    conn.jump_host = h.get("proxyjump", "")
    conn.group    = "Imported"
    return conn


class SshConfigImportDialog(QDialog):
    """
    Shows all Host entries found in an SSH config file and lets the
    user pick which ones to import into sshelf.
    """

    def __init__(self, db: Database, parent=None) -> None:
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Import from SSH Config")
        self.setMinimumSize(600, 420)
        self._hosts: list[dict] = []
        self._build_ui()
        self._load_default()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Path row
        path_row = QHBoxLayout()
        self._path_lbl = QLabel()
        self._path_lbl.setStyleSheet("color: #888; font-size: 11px;")
        path_row.addWidget(self._path_lbl, 1)
        btn_browse = QPushButton("Browse…")
        btn_browse.clicked.connect(self._browse)
        path_row.addWidget(btn_browse)
        layout.addLayout(path_row)

        # Tree
        self._tree = QTreeWidget()
        self._tree.setColumnCount(4)
        self._tree.setHeaderLabels(["Alias", "Hostname", "User", "Port"])
        self._tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._tree.setSelectionMode(self._tree.SelectionMode.NoSelection)
        layout.addWidget(self._tree)

        # Select all / none
        sel_row = QHBoxLayout()
        btn_all  = QPushButton("Select All")
        btn_none = QPushButton("Select None")
        btn_all.clicked.connect(self._select_all)
        btn_none.clicked.connect(self._select_none)
        sel_row.addWidget(btn_all)
        sel_row.addWidget(btn_none)
        sel_row.addStretch()
        layout.addLayout(sel_row)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        self._btn_import = QPushButton("Import Selected")
        self._btn_import.setDefault(True)
        self._btn_import.clicked.connect(self._do_import)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(self._btn_import)
        layout.addLayout(btn_row)

    def _load_default(self) -> None:
        default = Path.home() / ".ssh" / "config"
        if default.exists():
            self._load_file(default)
        else:
            self._path_lbl.setText("~/.ssh/config not found — use Browse")

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select SSH config file",
            str(Path.home() / ".ssh"),
            "Config files (config *);;All files (*)",
        )
        if path:
            self._load_file(Path(path))

    def _load_file(self, path: Path) -> None:
        self._path_lbl.setText(str(path))
        try:
            self._hosts = _parse_ssh_config(path)
        except Exception as e:
            QMessageBox.warning(self, "Parse error", str(e))
            return

        self._tree.clear()
        existing_hosts = {c.host for c in self.db.all_connections()}

        for h in self._hosts:
            item = QTreeWidgetItem([
                h.get("alias", ""),
                h.get("hostname", h.get("alias", "")),
                h.get("user", ""),
                str(h.get("port", 22)),
            ])
            item.setCheckState(0, Qt.CheckState.Unchecked)
            item.setData(0, Qt.ItemDataRole.UserRole, h)

            # Pre-check if not already imported; gray out if hostname matches existing
            hostname = h.get("hostname", h.get("alias", ""))
            if hostname in existing_hosts:
                item.setForeground(0, self._tree.palette().color(
                    self._tree.palette().ColorRole.PlaceholderText))
                item.setToolTip(0, "Already in your connections")
            else:
                item.setCheckState(0, Qt.CheckState.Checked)

            self._tree.addTopLevelItem(item)

        self._btn_import.setEnabled(bool(self._hosts))

    def _select_all(self) -> None:
        for i in range(self._tree.topLevelItemCount()):
            self._tree.topLevelItem(i).setCheckState(0, Qt.CheckState.Checked)

    def _select_none(self) -> None:
        for i in range(self._tree.topLevelItemCount()):
            self._tree.topLevelItem(i).setCheckState(0, Qt.CheckState.Unchecked)

    def _do_import(self) -> None:
        imported = 0
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            if item.checkState(0) == Qt.CheckState.Checked:
                h = item.data(0, Qt.ItemDataRole.UserRole)
                self.db.save_connection(_host_to_connection(h))
                imported += 1

        if imported:
            QMessageBox.information(
                self, "Import complete",
                f"Imported {imported} connection{'s' if imported != 1 else ''}.",
            )
            self.accept()
        else:
            QMessageBox.information(self, "Nothing selected", "Select at least one host to import.")
