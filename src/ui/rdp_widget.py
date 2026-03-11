"""RDP tab widget — status panel for an external RDP client session."""

from __future__ import annotations

import sys
from typing import Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
)

from src.models.connection import Connection
from src.storage.database import Database
from src.protocols.rdp_worker import RDPWorker


class RDPWidget(QWidget):
    """
    Tab widget for an RDP connection.

    The actual RDP session runs in an external window (xfreerdp / mstsc).
    This widget shows connection status and a reconnect bar.

    Interface matches SplitView/VNCWidget:
      all_closed, health_changed, status_message signals; shutdown() method.
    """

    all_closed     = pyqtSignal()
    health_changed = pyqtSignal(int, str)
    status_message = pyqtSignal(str)

    def __init__(
        self,
        conn:   Connection,
        db:     Database,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._conn   = conn
        self._db     = db
        self._thread: Optional[QThread]    = None
        self._worker: Optional[RDPWorker]  = None
        self._closed = False

        self._build_ui()
        self._start_connection()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Centre card
        centre = QWidget()
        centre.setSizePolicy(
            centre.sizePolicy().horizontalPolicy(),
            centre.sizePolicy().verticalPolicy(),
        )
        root.addStretch()
        root.addWidget(centre, alignment=Qt.AlignmentFlag.AlignHCenter)
        root.addStretch()

        card_lay = QVBoxLayout(centre)
        card_lay.setSpacing(12)
        card_lay.setContentsMargins(40, 32, 40, 32)

        # Title
        title = QLabel("🖥  Remote Desktop")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_lay.addWidget(title)

        card_lay.addWidget(_hline())

        # Connection details
        conn = self._conn
        port = conn.port if conn.port else 3389

        info_form = QVBoxLayout()
        info_form.setSpacing(6)

        def _row(label: str, value: str) -> QHBoxLayout:
            row = QHBoxLayout()
            lbl = QLabel(f"<b>{label}</b>")
            lbl.setFixedWidth(80)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            val = QLabel(value)
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row.addWidget(lbl)
            row.addWidget(val)
            row.addStretch()
            return row

        info_form.addLayout(_row("Host:", f"{conn.host}:{port}"))
        if conn.username:
            user = f"{conn.rdp_domain}\\{conn.username}" if conn.rdp_domain else conn.username
            info_form.addLayout(_row("User:", user))
        info_form.addLayout(_row("Resolution:", f"{conn.rdp_width}×{conn.rdp_height}"))
        info_form.addLayout(_row("Colour depth:", f"{conn.rdp_color_depth}-bit"))
        card_lay.addLayout(info_form)

        card_lay.addWidget(_hline())

        # Status
        self._status_lbl = QLabel("Connecting…")
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_lbl.setStyleSheet("color: palette(mid); font-size: 13px;")
        card_lay.addWidget(self._status_lbl)

        # Buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._btn_front = QPushButton("Bring to Front")
        self._btn_front.setFixedHeight(30)
        self._btn_front.clicked.connect(self._on_bring_to_front)
        self._btn_front.setVisible(False)
        btn_row.addWidget(self._btn_front)

        btn_close = QPushButton("Disconnect")
        btn_close.setFixedHeight(30)
        btn_close.clicked.connect(self._on_disconnect_clicked)
        btn_row.addWidget(btn_close)

        card_lay.addLayout(btn_row)

        # Platform hint
        hint = self._platform_hint()
        if hint:
            hint_lbl = QLabel(hint)
            hint_lbl.setWordWrap(True)
            hint_lbl.setStyleSheet("color: palette(mid); font-size: 11px;")
            hint_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            card_lay.addWidget(hint_lbl)

        # Reconnect bar (bottom)
        self._reconnect_bar = QWidget()
        self._reconnect_bar.setFixedHeight(36)
        self._reconnect_bar.setStyleSheet("background: #c0392b; color: white;")
        rb_lay = QHBoxLayout(self._reconnect_bar)
        rb_lay.setContentsMargins(12, 0, 12, 0)
        self._err_lbl = QLabel("Session ended")
        self._err_lbl.setStyleSheet("color: white;")
        rb_lay.addWidget(self._err_lbl)
        rb_lay.addStretch()
        btn_reconnect = QPushButton("↺  Reconnect")
        btn_reconnect.setStyleSheet(
            "background: rgba(255,255,255,0.2); color: white; "
            "border: 1px solid rgba(255,255,255,0.4); padding: 2px 10px;"
        )
        btn_reconnect.clicked.connect(self._on_reconnect_clicked)
        rb_lay.addWidget(btn_reconnect)
        self._reconnect_bar.setVisible(False)
        root.addWidget(self._reconnect_bar)

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _start_connection(self) -> None:
        self._reconnect_bar.setVisible(False)
        self._btn_front.setVisible(False)
        self._status_lbl.setText("Launching RDP client…")
        self._status_lbl.setStyleSheet("color: palette(mid); font-size: 13px;")

        self._thread = QThread(self)
        self._worker = RDPWorker(self._conn)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.connected.connect(self._on_connected)
        self._worker.error.connect(self._on_error)
        self._worker.disconnected.connect(self._on_disconnected)
        self._worker.disconnected.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)

        self._thread.start()

    def shutdown(self) -> None:
        self._closed = True
        if self._worker:
            self._worker.disconnect()
        if self._thread:
            self._thread.quit()
            self._thread.wait(2000)

    def matches_conn(self, conn: Connection) -> bool:
        return self._conn.id is not None and self._conn.id == conn.id

    # ------------------------------------------------------------------
    # Worker signals
    # ------------------------------------------------------------------

    def _on_connected(self) -> None:
        self._status_lbl.setText("● Session running in external window")
        self._status_lbl.setStyleSheet("color: #2ecc71; font-size: 13px;")
        self._btn_front.setVisible(True)
        if self._conn.id is not None:
            self.health_changed.emit(self._conn.id, "connected")
        self.status_message.emit(f"RDP session started: {self._conn.host}")

    def _on_error(self, msg: str) -> None:
        if self._closed:
            return
        self._status_lbl.setText("Error")
        self._status_lbl.setStyleSheet("color: #e74c3c; font-size: 13px;")
        self._err_lbl.setText(msg)
        self._reconnect_bar.setVisible(True)
        self._btn_front.setVisible(False)
        if self._conn.id is not None:
            self.health_changed.emit(self._conn.id, "error")

    def _on_disconnected(self, msg: str) -> None:
        if self._closed:
            return
        self._status_lbl.setText("Disconnected")
        self._status_lbl.setStyleSheet("color: palette(mid); font-size: 13px;")
        self._err_lbl.setText(msg or "Session ended")
        self._reconnect_bar.setVisible(True)
        self._btn_front.setVisible(False)
        if self._conn.id is not None:
            self.health_changed.emit(self._conn.id, "disconnected")

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------

    def _on_disconnect_clicked(self) -> None:
        self._closed = True
        if self._worker:
            self._worker.disconnect()
        if self._thread:
            self._thread.quit()
            self._thread.wait(2000)
        self.all_closed.emit()

    def _on_reconnect_clicked(self) -> None:
        self._closed = False
        if self._worker:
            self._worker.disconnect()
        if self._thread:
            self._thread.quit()
            self._thread.wait(2000)
        self._start_connection()

    def _on_bring_to_front(self) -> None:
        """Try to raise the xfreerdp window to the front."""
        if self._worker is None or self._worker._proc is None:
            return
        pid = self._worker._proc.pid
        try:
            if sys.platform == "darwin":
                import subprocess
                subprocess.Popen([
                    "osascript", "-e",
                    f"tell application \"System Events\" to set frontmost of "
                    f"the first process whose unix id is {pid} to true",
                ])
            elif sys.platform.startswith("linux"):
                import subprocess
                subprocess.Popen(
                    ["wmctrl", "-ia", f"{pid}"],
                    stderr=subprocess.DEVNULL,
                )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _platform_hint() -> str:
        if sys.platform == "darwin":
            return "Requires xfreerdp — install with: brew install freerdp"
        if sys.platform.startswith("linux"):
            return "Requires xfreerdp — install with: sudo apt install freerdp2-x11"
        return ""


def _hline() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    return line
