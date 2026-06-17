"""Add / Edit connection dialog — supports SSH, RDP, and VNC."""

from __future__ import annotations

import os
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout,
    QFormLayout, QTabWidget, QWidget, QLabel, QLineEdit,
    QSpinBox, QCheckBox, QTextEdit, QFileDialog, QPushButton,
    QComboBox, QColorDialog, QFrame,
)
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt

from src.storage.database import Database
from src.models.connection import Connection

# Tab indices (kept as constants so _on_protocol_changed is readable)
_TAB_BASIC    = 0
_TAB_AUTH     = 1
_TAB_ADVANCED = 2   # SSH only
_TAB_RDP      = 3   # RDP only
_TAB_VNC      = 4   # VNC only
_TAB_NOTES    = 5

# Default ports
_DEFAULT_PORTS = {"ssh": 22, "rdp": 3389, "vnc": 5900}


class ConnectionDialog(QDialog):
    """
    Modal dialog for creating or editing a connection.

    Tabs
    ----
    Basic      — protocol, name, group, host, port, username, colour
    Auth       — password; SSH key + passphrase (SSH only)
    Advanced   — jump host, startup cmd, keep-alive, SSH options  (SSH only)
    RDP Options — domain, resolution, colour depth                (RDP only)
    VNC Options — view-only checkbox                              (VNC only)
    Notes      — free-text notes
    """

    def __init__(
        self,
        db:         Database,
        connection: Optional[Connection] = None,
        parent:     QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.db    = db
        self._conn = connection or Connection()
        self.saved_connection: Connection = self._conn

        self.setWindowTitle("Edit Connection" if self._conn.id else "New Connection")
        self.setMinimumWidth(520)
        self.setModal(True)

        self._build_ui()
        self._load_values()
        # Apply initial protocol state after loading (so port is set correctly)
        self._on_protocol_changed(self._protocol.currentText().lower())

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)

        self._build_basic_tab()
        self._build_auth_tab()
        self._build_advanced_tab()
        self._build_rdp_tab()
        self._build_vnc_tab()
        self._build_notes_tab()

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _build_basic_tab(self) -> None:
        tab  = QWidget()
        form = QFormLayout(tab)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(10)
        form.setContentsMargins(16, 16, 16, 16)

        # Protocol selector — only shows protocols enabled in Preferences → Features
        self._protocol = QComboBox()
        _protocols = ["SSH"]
        if self.db.get_pref("enable_rdp", "0") == "1":
            _protocols.append("RDP")
        if self.db.get_pref("enable_vnc", "0") == "1":
            _protocols.append("VNC")
        self._protocol.addItems(_protocols)
        self._protocol.currentTextChanged.connect(
            lambda t: self._on_protocol_changed(t.lower())
        )
        form.addRow("Protocol:", self._protocol)

        form.addRow(_separator())

        self._name = QLineEdit()
        self._name.setPlaceholderText("My Server  (leave empty to use hostname)")
        form.addRow("Name:", self._name)

        self._group = QComboBox()
        self._group.setEditable(True)
        self._group.addItems(self.db.groups())
        self._group.lineEdit().setPlaceholderText("Default")
        form.addRow("Group:", self._group)

        form.addRow(_separator())

        self._host = QLineEdit()
        self._host.setPlaceholderText("192.168.1.1  or  dev.example.com")
        form.addRow("Host:", self._host)

        self._port = QSpinBox()
        self._port.setRange(1, 65535)
        self._port.setValue(22)
        form.addRow("Port:", self._port)

        self._username = QLineEdit()
        self._username.setPlaceholderText("your-user")
        form.addRow("Username:", self._username)

        form.addRow(_separator())

        # Colour picker
        colour_row = QHBoxLayout()
        self._colour_btn = QPushButton()
        self._colour_btn.setFixedSize(28, 28)
        self._colour_btn.setToolTip("Pick a colour label for this connection")
        self._colour_btn.clicked.connect(self._pick_colour)
        self._colour_value = ""
        self._apply_colour_btn()
        colour_row.addWidget(self._colour_btn)
        colour_row.addWidget(QLabel("Optional colour label"))
        colour_row.addStretch()
        form.addRow("Colour:", colour_row)

        self._tabs.addTab(tab, "Basic")

    def _build_auth_tab(self) -> None:
        tab  = QWidget()
        form = QFormLayout(tab)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(10)
        form.setContentsMargins(16, 16, 16, 16)

        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._password.setPlaceholderText("Leave blank to use key or agent (SSH)")
        form.addRow("Password:", self._password)

        form.addRow(_separator())

        # --- SSH-only section ---
        self._ssh_auth_sep = _separator()
        key_row = QHBoxLayout()
        self._key_file = QLineEdit()
        self._key_file.setPlaceholderText("~/.ssh/id_rsa")
        self._browse_btn = QPushButton("Browse…")
        self._browse_btn.setFixedWidth(80)
        self._browse_btn.clicked.connect(self._browse_key)
        key_row.addWidget(self._key_file)
        key_row.addWidget(self._browse_btn)

        self._key_label     = QLabel("Private Key:")
        self._key_widget    = _layout_widget(key_row)

        self._passphrase    = QLineEdit()
        self._passphrase.setEchoMode(QLineEdit.EchoMode.Password)
        self._passphrase.setPlaceholderText("Key passphrase (if any)")
        self._pass_label    = QLabel("Passphrase:")

        self._ssh_auth_note = QLabel(
            "Tip: if all fields are empty, paramiko will try your SSH agent "
            "and then ~/.ssh/id_rsa / id_ed25519 automatically."
        )
        self._ssh_auth_note.setWordWrap(True)
        self._ssh_auth_note.setStyleSheet("color: palette(mid);")

        form.addRow(self._key_label, self._key_widget)
        form.addRow(self._pass_label, self._passphrase)
        form.addRow("", self._ssh_auth_note)

        self._tabs.addTab(tab, "Auth")

    def _build_advanced_tab(self) -> None:
        tab  = QWidget()
        form = QFormLayout(tab)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(10)
        form.setContentsMargins(16, 16, 16, 16)

        self._jump_host = QLineEdit()
        self._jump_host.setPlaceholderText("user@bastion.example.com:22")
        form.addRow("Jump Host:", self._jump_host)

        self._startup_cmd = QLineEdit()
        self._startup_cmd.setPlaceholderText("tmux attach  or  bash --login")
        form.addRow("Startup Command:", self._startup_cmd)

        form.addRow(_separator())

        self._keep_alive = QSpinBox()
        self._keep_alive.setRange(0, 3600)
        self._keep_alive.setSuffix(" s")
        self._keep_alive.setValue(60)
        self._keep_alive.setToolTip("Set 0 to disable keep-alive packets")
        form.addRow("Keep-Alive:", self._keep_alive)

        form.addRow(_separator())

        self._agent_forward = QCheckBox("Forward SSH agent")
        form.addRow("Agent:", self._agent_forward)

        self._x11 = QCheckBox("Enable X11 forwarding")
        form.addRow("X11:", self._x11)

        self._compress = QCheckBox("Enable compression")
        form.addRow("Compression:", self._compress)

        self._tabs.addTab(tab, "Advanced")

    def _build_rdp_tab(self) -> None:
        tab  = QWidget()
        form = QFormLayout(tab)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(10)
        form.setContentsMargins(16, 16, 16, 16)

        self._rdp_domain = QLineEdit()
        self._rdp_domain.setPlaceholderText("CORP  (leave empty for local account)")
        form.addRow("Domain:", self._rdp_domain)

        form.addRow(_separator())

        # Resolution
        res_row = QHBoxLayout()
        self._rdp_width = QSpinBox()
        self._rdp_width.setRange(640, 7680)
        self._rdp_width.setValue(1920)
        self._rdp_width.setSuffix(" px")
        res_row.addWidget(self._rdp_width)
        res_row.addWidget(QLabel("×"))
        self._rdp_height = QSpinBox()
        self._rdp_height.setRange(480, 4320)
        self._rdp_height.setValue(1080)
        self._rdp_height.setSuffix(" px")
        res_row.addWidget(self._rdp_height)
        res_row.addStretch()
        form.addRow("Resolution:", _layout_widget(res_row))

        self._rdp_depth = QComboBox()
        for d in ("8-bit", "16-bit", "24-bit", "32-bit"):
            self._rdp_depth.addItem(d)
        self._rdp_depth.setCurrentIndex(3)  # 32-bit
        form.addRow("Colour depth:", self._rdp_depth)

        form.addRow(_separator())

        note = QLabel(
            "Requires xfreerdp on macOS/Linux (brew install freerdp) "
            "or uses mstsc.exe on Windows."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: palette(mid);")
        form.addRow("", note)

        self._tabs.addTab(tab, "RDP Options")

    def _build_vnc_tab(self) -> None:
        tab  = QWidget()
        form = QFormLayout(tab)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(10)
        form.setContentsMargins(16, 16, 16, 16)

        self._vnc_view_only = QCheckBox("View only (no keyboard or mouse input)")
        form.addRow("Mode:", self._vnc_view_only)

        form.addRow(_separator())

        note = QLabel(
            "Password (set in the Auth tab) is the VNC password used for "
            "authentication.  Leave blank for unauthenticated servers."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: palette(mid);")
        form.addRow("", note)

        self._tabs.addTab(tab, "VNC Options")

    def _build_notes_tab(self) -> None:
        tab    = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.addWidget(QLabel("Free-text notes for this connection:"))
        self._notes = QTextEdit()
        self._notes.setAcceptRichText(False)
        layout.addWidget(self._notes)
        self._tabs.addTab(tab, "Notes")

    # ------------------------------------------------------------------
    # Protocol switching
    # ------------------------------------------------------------------

    def _on_protocol_changed(self, protocol: str) -> None:
        """Show/hide tabs and adjust defaults when the protocol changes."""
        is_ssh = protocol == "ssh"
        is_rdp = protocol == "rdp"
        is_vnc = protocol == "vnc"

        # Tab visibility
        self._tabs.setTabVisible(_TAB_ADVANCED, is_ssh)
        self._tabs.setTabVisible(_TAB_RDP,      is_rdp)
        self._tabs.setTabVisible(_TAB_VNC,      is_vnc)

        # SSH-only auth fields
        for w in (self._key_label, self._key_widget,
                  self._pass_label, self._passphrase,
                  self._ssh_auth_note):
            w.setVisible(is_ssh)

        # Password label changes by protocol
        if is_vnc:
            self._password.setPlaceholderText("VNC password (leave blank for none)")
        elif is_rdp:
            self._password.setPlaceholderText("RDP password")
        else:
            self._password.setPlaceholderText("Leave blank to use key or agent")

        # Update port default if still at a known default value
        current_port = self._port.value()
        for p in _DEFAULT_PORTS.values():
            if current_port == p:
                self._port.setValue(_DEFAULT_PORTS[protocol])
                break

    # ------------------------------------------------------------------
    # Load / save values
    # ------------------------------------------------------------------

    def _load_values(self) -> None:
        c = self._conn

        # Protocol
        proto_map = {"ssh": "SSH", "rdp": "RDP", "vnc": "VNC"}
        idx = self._protocol.findText(proto_map.get(c.protocol, "SSH"))
        if idx >= 0:
            self._protocol.setCurrentIndex(idx)

        self._name.setText(c.name)
        if c.group and c.group not in [self._group.itemText(i) for i in range(self._group.count())]:
            self._group.addItem(c.group)
        self._group.setCurrentText(c.group)

        self._host.setText(c.host)
        self._port.setValue(c.port if c.port else _DEFAULT_PORTS.get(c.protocol, 22))
        self._username.setText(c.username)
        self._colour_value = c.color
        self._apply_colour_btn()

        self._password.setText(c.password)
        self._key_file.setText(c.private_key_file)
        self._passphrase.setText(c.passphrase)

        self._jump_host.setText(c.jump_host)
        self._startup_cmd.setText(c.startup_command)
        self._keep_alive.setValue(c.keep_alive_interval)
        self._agent_forward.setChecked(c.forward_agent)
        self._x11.setChecked(c.x11_forward)
        self._compress.setChecked(c.compression)

        self._rdp_domain.setText(c.rdp_domain)
        self._rdp_width.setValue(c.rdp_width)
        self._rdp_height.setValue(c.rdp_height)
        depth_idx = {8: 0, 16: 1, 24: 2, 32: 3}.get(c.rdp_color_depth, 3)
        self._rdp_depth.setCurrentIndex(depth_idx)

        self._vnc_view_only.setChecked(c.vnc_view_only)

        self._notes.setPlainText(c.notes)

    def _save_values(self) -> None:
        c = self._conn
        c.protocol  = self._protocol.currentText().lower()
        c.name      = self._name.text().strip()
        c.group     = self._group.currentText().strip() or "Default"
        c.host      = self._host.text().strip()
        c.port      = self._port.value()
        c.username  = self._username.text().strip()
        c.color     = self._colour_value

        c.password  = self._password.text()

        # SSH
        c.private_key_file   = self._key_file.text().strip()
        c.passphrase         = self._passphrase.text()
        c.jump_host          = self._jump_host.text().strip()
        c.startup_command    = self._startup_cmd.text().strip()
        c.keep_alive_interval = self._keep_alive.value()
        c.forward_agent      = self._agent_forward.isChecked()
        c.x11_forward        = self._x11.isChecked()
        c.compression        = self._compress.isChecked()

        # RDP
        c.rdp_domain      = self._rdp_domain.text().strip()
        c.rdp_width       = self._rdp_width.value()
        c.rdp_height      = self._rdp_height.value()
        c.rdp_color_depth = [8, 16, 24, 32][self._rdp_depth.currentIndex()]

        # VNC
        c.vnc_view_only = self._vnc_view_only.isChecked()

        c.notes = self._notes.toPlainText().strip()

    # ------------------------------------------------------------------
    # Validation and accept
    # ------------------------------------------------------------------

    def _on_accept(self) -> None:
        host = self._host.text().strip()
        if not host:
            self._tabs.setCurrentIndex(0)
            self._host.setFocus()
            self._host.setStyleSheet("border: 1px solid #e74c3c;")
            return
        self._host.setStyleSheet("")
        self._save_values()
        self.saved_connection = self.db.save_connection(self._conn)
        self.accept()

    # ------------------------------------------------------------------
    # Helper actions
    # ------------------------------------------------------------------

    def _browse_key(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Private Key File",
            str(os.path.expanduser("~/.ssh")),
            "All Files (*)",
        )
        if path:
            self._key_file.setText(path)

    def _pick_colour(self) -> None:
        initial = QColor(self._colour_value) if self._colour_value else QColor("#4caf50")
        colour  = QColorDialog.getColor(initial, self, "Choose Connection Colour")
        if colour.isValid():
            self._colour_value = colour.name()
            self._apply_colour_btn()

    def _apply_colour_btn(self) -> None:
        if self._colour_value:
            self._colour_btn.setStyleSheet(
                f"background-color: {self._colour_value}; border-radius: 4px;"
            )
        else:
            self._colour_btn.setStyleSheet(
                "background-color: palette(button); border-radius: 4px;"
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _separator() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    return line


def _layout_widget(layout: QHBoxLayout) -> QWidget:
    """Wrap an HBoxLayout in a plain QWidget so it can be added to QFormLayout."""
    w = QWidget()
    w.setLayout(layout)
    return w
