"""Port-forwarding side panel.

Shows tunnel rules for the current connection and lets the user
add / remove / toggle them.  Tunnel workers are started/stopped
as the SSH session connects or disconnects.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from src.models.tunnel import Tunnel


# ── Add-tunnel dialog ─────────────────────────────────────────────────────────

class _TunnelDialog(QDialog):
    """Simple dialog for creating or editing a Tunnel."""

    def __init__(self, tunnel: Tunnel | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Tunnel" if tunnel is None else "Edit Tunnel")
        self.setMinimumWidth(340)
        self.setModal(True)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)
        form.setContentsMargins(12, 12, 12, 8)

        self._label = QLineEdit(tunnel.label if tunnel else "")
        self._label.setPlaceholderText("e.g. PostgreSQL")
        form.addRow("Label:", self._label)

        self._type = QComboBox()
        self._type.addItems(["local", "remote"])
        if tunnel:
            self._type.setCurrentText(tunnel.type)
        form.addRow("Type:", self._type)

        self._local_port = QSpinBox()
        self._local_port.setRange(1, 65535)
        self._local_port.setValue(tunnel.local_port if tunnel else 5432)
        form.addRow("Local port:", self._local_port)

        self._remote_host = QLineEdit(tunnel.remote_host if tunnel else "")
        self._remote_host.setPlaceholderText("e.g. 127.0.0.1")
        form.addRow("Remote host:", self._remote_host)

        self._remote_port = QSpinBox()
        self._remote_port.setRange(1, 65535)
        self._remote_port.setValue(tunnel.remote_port if tunnel else 5432)
        form.addRow("Remote port:", self._remote_port)

        layout.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def result_tunnel(self) -> Tunnel:
        """Return a new Tunnel instance (id=None) from the form values."""
        return Tunnel(
            id=None,
            conn_id=0,          # caller sets this
            label=self._label.text().strip() or "Tunnel",
            type=self._type.currentText(),
            local_port=self._local_port.value(),
            remote_host=self._remote_host.text().strip() or "127.0.0.1",
            remote_port=self._remote_port.value(),
            enabled=True,
        )


# ── Tunnel panel ──────────────────────────────────────────────────────────────

class TunnelPanel(QWidget):
    """
    Side panel that lists port-forwarding tunnels for one SSH connection.

    Usage
    -----
    panel = TunnelPanel(db=db, conn_id=conn.id, parent=self)
    # When SSH connects:
    panel.set_worker(ssh_worker)
    # When SSH disconnects:
    panel.set_worker(None)
    """

    def __init__(self, db, conn_id: int | None, parent=None) -> None:
        super().__init__(parent)
        self._db = db
        self._conn_id = conn_id
        self._worker = None
        self._active_workers: list = []   # running Local/RemoteTunnelWorker instances

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Status label
        self._status_lbl = QLabel("SSH not connected")
        self._status_lbl.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self._status_lbl)

        # Tunnel list
        self._list = QListWidget()
        self._list.setStyleSheet(
            "QListWidget { background: #1e1e1e; border: 1px solid #333; }"
            "QListWidget::item { padding: 4px 6px; color: #ccc; }"
            "QListWidget::item:selected { background: #2c5282; }"
        )
        layout.addWidget(self._list, stretch=1)

        # Buttons
        btn_row = QHBoxLayout()
        btn_add = QPushButton("＋ Add")
        btn_add.clicked.connect(self._on_add)
        btn_row.addWidget(btn_add)

        self._btn_remove = QPushButton("⌫ Remove")
        self._btn_remove.setEnabled(False)
        self._btn_remove.clicked.connect(self._on_remove)
        btn_row.addWidget(self._btn_remove)

        self._btn_toggle = QPushButton("Enable")
        self._btn_toggle.setEnabled(False)
        self._btn_toggle.clicked.connect(self._on_toggle)
        btn_row.addWidget(self._btn_toggle)

        layout.addLayout(btn_row)

        self._list.currentRowChanged.connect(self._on_selection_changed)
        self._reload()

    # ── Public API ─────────────────────────────────────────────────────────────

    def set_worker(self, worker) -> None:
        """
        Call with the SSHWorker when the session connects, or None when it closes.
        Starts all enabled tunnels on connect; stops them all on disconnect.
        """
        self._worker = worker
        self._stop_all_active()
        if worker is not None:
            self._status_lbl.setText("Connected — tunnels active")
            self._status_lbl.setStyleSheet("color: #98c379; font-size: 11px;")
            self._start_enabled_tunnels()
        else:
            self._status_lbl.setText("SSH not connected")
            self._status_lbl.setStyleSheet("color: #888; font-size: 11px;")
        self._reload()

    # ── Internal ───────────────────────────────────────────────────────────────

    def _reload(self) -> None:
        """Refresh the list from the DB."""
        self._list.clear()
        if self._conn_id is None or self._db is None:
            return
        for row in self._db.all_tunnels(self._conn_id):
            t = Tunnel.from_dict(row)
            item = QListWidgetItem(self._item_text(t))
            item.setData(Qt.ItemDataRole.UserRole, t)
            if not t.enabled:
                item.setForeground(Qt.GlobalColor.darkGray)
            self._list.addItem(item)
        self._on_selection_changed(self._list.currentRow())

    def _item_text(self, t: Tunnel) -> str:
        status = "●" if (t.enabled and self._worker is not None) else "○"
        return (
            f"{status}  {t.label}  "
            f"[{t.type}]  :{t.local_port} → {t.remote_host}:{t.remote_port}"
        )

    def _on_selection_changed(self, row: int) -> None:
        has = row >= 0
        self._btn_remove.setEnabled(has)
        if has:
            item = self._list.item(row)
            t: Tunnel = item.data(Qt.ItemDataRole.UserRole)
            self._btn_toggle.setEnabled(True)
            self._btn_toggle.setText("Disable" if t.enabled else "Enable")
        else:
            self._btn_toggle.setEnabled(False)
            self._btn_toggle.setText("Enable")

    def _on_add(self) -> None:
        if self._conn_id is None:
            return
        dlg = _TunnelDialog(parent=self)
        if dlg.exec():
            t = dlg.result_tunnel()
            t.conn_id = self._conn_id
            self._db.save_tunnel(t)
            if t.enabled and self._worker is not None:
                self._launch_worker(t)
            self._reload()

    def _on_remove(self) -> None:
        item = self._list.currentItem()
        if not item:
            return
        t: Tunnel = item.data(Qt.ItemDataRole.UserRole)
        if t.id is not None:
            self._db.delete_tunnel(t.id)
        self._reload()

    def _on_toggle(self) -> None:
        item = self._list.currentItem()
        if not item:
            return
        t: Tunnel = item.data(Qt.ItemDataRole.UserRole)
        t.enabled = not t.enabled
        if t.id is not None:
            self._db.save_tunnel(t)
        if t.enabled and self._worker is not None:
            self._launch_worker(t)
        self._reload()

    # ── Worker management ──────────────────────────────────────────────────────

    def _start_enabled_tunnels(self) -> None:
        if self._conn_id is None or self._db is None:
            return
        for row in self._db.all_tunnels(self._conn_id):
            t = Tunnel.from_dict(row)
            if t.enabled:
                self._launch_worker(t)

    def _launch_worker(self, tunnel: Tunnel) -> None:
        """Start a Local or Remote tunnel worker for *tunnel*."""
        if self._worker is None:
            return
        transport = self._worker.get_transport()
        if transport is None:
            return

        try:
            from src.protocols.tunnel_worker import (
                LocalTunnelWorker, RemoteTunnelWorker,
            )
            if tunnel.type == "local":
                w = LocalTunnelWorker(
                    transport,
                    tunnel.local_port,
                    tunnel.remote_host,
                    tunnel.remote_port,
                )
            else:
                w = RemoteTunnelWorker(
                    transport,
                    tunnel.local_port,
                    tunnel.remote_host,
                    tunnel.remote_port,
                )
            w.start()
            self._active_workers.append(w)
        except Exception:  # noqa: BLE001
            pass

    def _stop_all_active(self) -> None:
        for w in list(self._active_workers):
            try:
                w.stop()
            except Exception:  # noqa: BLE001
                pass
        self._active_workers.clear()
