"""Embedded SSH terminal widget."""

from __future__ import annotations

import re
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit
from PyQt6.QtGui import QFont, QTextCursor, QKeyEvent, QColor, QPalette, QTextCharFormat
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from src.models.connection import Connection
from src.protocols.ssh import SSHWorker

# Regex to strip ANSI escape sequences for the basic renderer
_ANSI_RE = re.compile(r'\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')


class TerminalWidget(QWidget):
    """
    Right-panel widget that embeds an interactive SSH session.

    Architecture:
      - SSHWorker runs in a QThread
      - Incoming bytes are ANSI-stripped and appended to QPlainTextEdit
      - Key events are forwarded to SSHWorker.send()
    """

    status_message = pyqtSignal(str)
    disconnected = pyqtSignal(str)

    def __init__(self, connection: Connection, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._conn = connection
        self._thread: QThread | None = None
        self._worker: SSHWorker | None = None

        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header bar
        header = QWidget()
        header.setStyleSheet("background: #2b2b2b;")
        header.setFixedHeight(32)
        hbar = QHBoxLayout(header)
        hbar.setContentsMargins(10, 0, 10, 0)

        self._title_lbl = QLabel(f"🔑  {self._conn.connection_string()}")
        self._title_lbl.setStyleSheet("color: #ccc; font-size: 12px;")
        hbar.addWidget(self._title_lbl)
        hbar.addStretch()

        btn_disc = QPushButton("✕ Disconnect")
        btn_disc.setStyleSheet(
            "QPushButton { color: #f55; background: transparent; border: none; }"
            "QPushButton:hover { color: #fff; }"
        )
        btn_disc.clicked.connect(self._on_disconnect)
        hbar.addWidget(btn_disc)

        layout.addWidget(header)

        # Terminal output area
        self._output = _TerminalEdit(self)
        self._output.key_pressed.connect(self._on_key)
        layout.addWidget(self._output)

        # Status bar
        self._status = QLabel("Connecting…")
        self._status.setStyleSheet(
            "background: #1e1e1e; color: #888; padding: 2px 8px; font-size: 11px;"
        )
        layout.addWidget(self._status)

    def _set_status(self, msg: str) -> None:
        self._status.setText(msg)
        self.status_message.emit(msg)

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def start_connection(self) -> None:
        self._thread = QThread(self)
        self._worker = SSHWorker(self._conn)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.connected.connect(self._on_connected)
        self._worker.data_received.connect(self._on_data)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._on_finished)

        self._thread.start()

    def _on_disconnect(self) -> None:
        if self._worker:
            self._worker.disconnect()
        self._set_status("Disconnected.")

    # ------------------------------------------------------------------
    # Worker signals
    # ------------------------------------------------------------------

    def _on_connected(self) -> None:
        self._set_status(f"Connected to {self._conn.connection_string()}")
        self._output.setFocus()

    def _on_data(self, raw: bytes) -> None:
        text = raw.decode("utf-8", errors="replace")
        text = _ANSI_RE.sub("", text)
        self._output.append_text(text)

    def _on_error(self, msg: str) -> None:
        self._set_status(f"Error: {msg}")
        self._output.append_text(f"\r\n\033[31m*** {msg} ***\033[0m\r\n")
        self.disconnected.emit(f"Error: {msg}")

    def _on_finished(self) -> None:
        self._set_status("Session closed.")
        self._output.append_text("\r\n[Session closed]\r\n")
        if self._thread:
            self._thread.quit()
        self.disconnected.emit("Session closed.")

    # ------------------------------------------------------------------
    # Keyboard input forwarding
    # ------------------------------------------------------------------

    def _on_key(self, data: bytes) -> None:
        if self._worker:
            self._worker.send(data)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        self._on_disconnect()
        if self._thread:
            self._thread.quit()
            self._thread.wait(2000)
        super().closeEvent(event)


class _TerminalEdit(QPlainTextEdit):
    """
    Read-only display with special key capture.
    Keys are NOT inserted locally — they are sent to the SSH worker
    and the server's echo appears as incoming data.
    """

    key_pressed = pyqtSignal(bytes)

    # Maps Qt key codes → ANSI escape sequences
    _KEY_MAP = {
        Qt.Key.Key_Up:        b"\x1b[A",
        Qt.Key.Key_Down:      b"\x1b[B",
        Qt.Key.Key_Right:     b"\x1b[C",
        Qt.Key.Key_Left:      b"\x1b[D",
        Qt.Key.Key_Home:      b"\x1b[H",
        Qt.Key.Key_End:       b"\x1b[F",
        Qt.Key.Key_PageUp:    b"\x1b[5~",
        Qt.Key.Key_PageDown:  b"\x1b[6~",
        Qt.Key.Key_Delete:    b"\x1b[3~",
        Qt.Key.Key_F1:        b"\x1bOP",
        Qt.Key.Key_F2:        b"\x1bOQ",
        Qt.Key.Key_F3:        b"\x1bOR",
        Qt.Key.Key_F4:        b"\x1bOS",
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setUndoRedoEnabled(False)

        font = QFont("Menlo", 13)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)

        # Dark terminal palette
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Base, QColor("#1e1e1e"))
        pal.setColor(QPalette.ColorRole.Text, QColor("#d4d4d4"))
        self.setPalette(pal)
        self.setStyleSheet("border: none; padding: 6px;")
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

    def append_text(self, text: str) -> None:
        """Append text without adding an extra newline (unlike appendPlainText)."""
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        mods = event.modifiers()
        text = event.text()

        # Ctrl+C / Ctrl+D etc.
        if mods & Qt.KeyboardModifier.ControlModifier:
            char = text.lower()
            if char:
                code = ord(char) - ord('a') + 1
                if 1 <= code <= 26:
                    self.key_pressed.emit(bytes([code]))
                    return

        if key in self._KEY_MAP:
            self.key_pressed.emit(self._KEY_MAP[key])
            return

        if key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
            self.key_pressed.emit(b"\r")
            return

        if key == Qt.Key.Key_Backspace:
            self.key_pressed.emit(b"\x7f")
            return

        if key == Qt.Key.Key_Tab:
            self.key_pressed.emit(b"\t")
            return

        if key == Qt.Key.Key_Escape:
            self.key_pressed.emit(b"\x1b")
            return

        if text:
            self.key_pressed.emit(text.encode("utf-8", errors="replace"))
