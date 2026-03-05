"""SSH key-pair generation dialog."""

from __future__ import annotations

import re
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QDialogButtonBox,
    QComboBox, QLineEdit, QPushButton, QLabel, QHBoxLayout,
    QCheckBox, QMessageBox, QApplication,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt6.QtGui import QFont


# ── Background key-generation worker ─────────────────────────────────────────

class _KeyGenWorker(QObject):
    finished = pyqtSignal(str, str)  # private_key_path, public_key_text
    error    = pyqtSignal(str)

    def __init__(self, key_type: str, bits: int,
                 path: str, passphrase: str) -> None:
        super().__init__()
        self._key_type  = key_type
        self._bits      = bits
        self._path      = path
        self._passphrase = passphrase or None

    def run(self) -> None:
        import paramiko
        try:
            if self._key_type == "ed25519":
                key = paramiko.Ed25519Key.generate()
            elif self._key_type == "ecdsa":
                key = paramiko.ECDSAKey.generate(bits=self._bits)
            else:
                key = paramiko.RSAKey.generate(self._bits)

            path = Path(self._path).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            key.write_private_key_file(str(path), password=self._passphrase)

            pub_path = path.with_suffix(".pub") if path.suffix == "" else Path(str(path) + ".pub")
            pub_text = f"{key.get_name()} {key.get_base64()} RemminaMac-generated"
            pub_path.write_text(pub_text + "\n")
            path.chmod(0o600)

            self.finished.emit(str(path), pub_text)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))


# ── Dialog ────────────────────────────────────────────────────────────────────

class KeyGenerationDialog(QDialog):
    """
    Generates an SSH key pair and saves it to ~/.ssh/.

    Features
    --------
    - Key type: ed25519 (recommended), ECDSA-256/384/521, RSA-2048/4096
    - Optional passphrase
    - Saves private key to ~/.ssh/<name>, public key to ~/.ssh/<name>.pub
    - One-click copy of the public key to clipboard
    - Optional: show the ssh-copy-id command to push the key to a server
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Generate SSH Key Pair")
        self.setMinimumWidth(480)
        self.setModal(True)

        self._worker: _KeyGenWorker | None = None
        self._thread: QThread | None = None
        self._pub_key_text = ""

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)

        # Key type
        self._key_type = QComboBox()
        self._key_type.addItems(["ed25519 (recommended)", "ECDSA-256", "ECDSA-384",
                                  "ECDSA-521", "RSA-2048", "RSA-4096"])
        form.addRow("Key type:", self._key_type)

        # Filename
        fn_row = QHBoxLayout()
        self._filename = QLineEdit("id_ed25519")
        fn_row.addWidget(self._filename)
        fn_lbl = QLabel("  saved to ~/.ssh/")
        fn_lbl.setStyleSheet("color: #888;")
        fn_row.addWidget(fn_lbl)
        form.addRow("Filename:", fn_row)

        # Passphrase
        self._passphrase = QLineEdit()
        self._passphrase.setEchoMode(QLineEdit.EchoMode.Password)
        self._passphrase.setPlaceholderText("Leave blank for no passphrase")
        form.addRow("Passphrase:", self._passphrase)

        self._passphrase2 = QLineEdit()
        self._passphrase2.setEchoMode(QLineEdit.EchoMode.Password)
        self._passphrase2.setPlaceholderText("Confirm passphrase")
        form.addRow("Confirm:", self._passphrase2)

        layout.addLayout(form)

        # Generate button
        self._btn_generate = QPushButton("⚙  Generate Key Pair")
        self._btn_generate.setStyleSheet(
            "QPushButton{background:#0066cc;color:white;border-radius:4px;"
            "border:none;padding:6px 16px;font-weight:bold;}"
            "QPushButton:hover{background:#0080ff;}"
            "QPushButton:disabled{background:#444;color:#888;}"
        )
        self._btn_generate.clicked.connect(self._start_generation)
        layout.addWidget(self._btn_generate)

        # Status / public key display
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self._status_lbl)

        self._pubkey_box = QLineEdit()
        self._pubkey_box.setReadOnly(True)
        self._pubkey_box.setPlaceholderText("Public key will appear here after generation")
        f = QFont("Menlo", 10)
        self._pubkey_box.setFont(f)
        self._pubkey_box.setStyleSheet("background: #2b2b2b; color: #98c379;")
        layout.addWidget(self._pubkey_box)

        # Copy / copy-id buttons
        btn_row = QHBoxLayout()
        self._btn_copy = QPushButton("📋  Copy Public Key")
        self._btn_copy.setEnabled(False)
        self._btn_copy.clicked.connect(self._copy_pubkey)
        btn_row.addWidget(self._btn_copy)

        self._btn_copy_cmd = QPushButton("📋  Copy ssh-copy-id Command")
        self._btn_copy_cmd.setEnabled(False)
        self._btn_copy_cmd.clicked.connect(self._copy_copy_id_cmd)
        btn_row.addWidget(self._btn_copy_cmd)
        layout.addLayout(btn_row)

        # Close button
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        # Update filename suggestion when key type changes
        self._key_type.currentIndexChanged.connect(self._update_filename_hint)

    # ------------------------------------------------------------------

    def _update_filename_hint(self) -> None:
        t = self._key_type.currentText()
        if "ed25519" in t:
            self._filename.setText("id_ed25519")
        elif "ecdsa" in t.lower():
            self._filename.setText("id_ecdsa")
        else:
            self._filename.setText("id_rsa")

    def _start_generation(self) -> None:
        pp = self._passphrase.text()
        if pp != self._passphrase2.text():
            QMessageBox.warning(self, "Passphrase Mismatch",
                                "Passphrases do not match.")
            return

        fname = self._filename.text().strip()
        if not fname or not re.match(r'^[\w.\-]+$', fname):
            QMessageBox.warning(self, "Invalid Filename",
                                "Filename may only contain letters, numbers, hyphens, underscores, dots.")
            return

        path = str(Path("~/.ssh") / fname)
        full = Path(path).expanduser()
        if full.exists():
            r = QMessageBox.question(
                self, "File Exists",
                f"{full} already exists. Overwrite?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            )
            if r != QMessageBox.StandardButton.Yes:
                return

        t = self._key_type.currentText()
        if "ed25519" in t:
            key_type, bits = "ed25519", 0
        elif "ECDSA-256" in t:
            key_type, bits = "ecdsa", 256
        elif "ECDSA-384" in t:
            key_type, bits = "ecdsa", 384
        elif "ECDSA-521" in t:
            key_type, bits = "ecdsa", 521
        elif "RSA-2048" in t:
            key_type, bits = "rsa", 2048
        else:
            key_type, bits = "rsa", 4096

        self._btn_generate.setEnabled(False)
        self._status_lbl.setText("⏳  Generating key pair…")
        self._pubkey_box.clear()
        self._btn_copy.setEnabled(False)
        self._btn_copy_cmd.setEnabled(False)

        self._thread = QThread(self)
        self._worker = _KeyGenWorker(key_type, bits, path, pp)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_generated)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.start()

    def _on_generated(self, priv_path: str, pub_text: str) -> None:
        self._pub_key_text = pub_text
        self._pubkey_box.setText(pub_text)
        self._status_lbl.setText(f"✅  Key pair saved to {priv_path}")
        self._btn_generate.setEnabled(True)
        self._btn_copy.setEnabled(True)
        self._btn_copy_cmd.setEnabled(True)

    def _on_error(self, msg: str) -> None:
        self._status_lbl.setText(f"❌  Error: {msg}")
        self._btn_generate.setEnabled(True)

    def _copy_pubkey(self) -> None:
        QApplication.clipboard().setText(self._pub_key_text)
        self._btn_copy.setText("✅  Copied!")

    def _copy_copy_id_cmd(self) -> None:
        fname = self._filename.text().strip()
        cmd = f"ssh-copy-id -i ~/.ssh/{fname}.pub user@hostname"
        QApplication.clipboard().setText(cmd)
        self._btn_copy_cmd.setText("✅  Copied!")
