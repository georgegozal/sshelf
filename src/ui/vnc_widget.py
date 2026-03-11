"""VNC tab widget — renders a remote RFB framebuffer inside a PyQt6 QWidget."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QRect, QThread, pyqtSignal
from PyQt6.QtGui import QImage, QPainter, QColor, QKeyEvent, QMouseEvent, QWheelEvent
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
    QFrame,
)

from src.models.connection import Connection
from src.storage.database import Database
from src.protocols.vnc_worker import VNCWorker, qt_key_to_keysym


# ---------------------------------------------------------------------------
# Canvas
# ---------------------------------------------------------------------------

class _VNCCanvas(QWidget):
    """Renders the VNC framebuffer and forwards input to the worker."""

    key_pressed   = pyqtSignal(int, str)   # Qt key, text
    key_released  = pyqtSignal(int, str)
    pointer_event = pyqtSignal(int, int, int)  # x, y, button_mask

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(320, 200)

        self._image:       Optional[QImage]    = None
        self._fb:          Optional[bytearray] = None
        self._img_w        = 0
        self._img_h        = 0
        self._button_mask  = 0
        self._view_only    = False

    # ------------------------------------------------------------------
    # Framebuffer management
    # ------------------------------------------------------------------

    def init_framebuffer(self, width: int, height: int) -> None:
        self._img_w = width
        self._img_h = height
        self._fb    = bytearray(width * height * 4)
        self._image = QImage(
            self._fb, width, height,
            QImage.Format.Format_RGB32,
        )
        self.update()

    def apply_frame(self, x: int, y: int, w: int, h: int, data: bytes) -> None:
        if self._fb is None or self._image is None:
            return
        stride  = self._img_w * 4
        row_w   = w * 4
        for row in range(h):
            dst = (y + row) * stride + x * 4
            src = row * row_w
            self._fb[dst: dst + row_w] = data[src: src + row_w]
        self.update()

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        if self._image is None:
            painter = QPainter(self)
            painter.fillRect(self.rect(), QColor("#1a1a2e"))
            painter.setPen(QColor("#555"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Connecting…")
            return

        painter = QPainter(self)
        target  = self.rect()
        # Scale keeping aspect ratio, centred
        scale   = min(target.width() / self._img_w, target.height() / self._img_h)
        dw      = int(self._img_w * scale)
        dh      = int(self._img_h * scale)
        ox      = (target.width()  - dw) // 2
        oy      = (target.height() - dh) // 2
        painter.drawImage(QRect(ox, oy, dw, dh), self._image)

    # ------------------------------------------------------------------
    # Coordinate mapping
    # ------------------------------------------------------------------

    def _map_pos(self, px: int, py: int) -> tuple[int, int]:
        if self._image is None:
            return 0, 0
        scale = min(self.width() / self._img_w, self.height() / self._img_h)
        dw    = int(self._img_w * scale)
        dh    = int(self._img_h * scale)
        ox    = (self.width()  - dw) // 2
        oy    = (self.height() - dh) // 2
        rx    = int((px - ox) / scale)
        ry    = int((py - oy) / scale)
        return (
            max(0, min(rx, self._img_w - 1)),
            max(0, min(ry, self._img_h - 1)),
        )

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._view_only:
            return
        btn = event.button()
        if btn == Qt.MouseButton.LeftButton:
            self._button_mask |= 0x01
        elif btn == Qt.MouseButton.MiddleButton:
            self._button_mask |= 0x02
        elif btn == Qt.MouseButton.RightButton:
            self._button_mask |= 0x04
        rx, ry = self._map_pos(int(event.position().x()), int(event.position().y()))
        self.pointer_event.emit(rx, ry, self._button_mask)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._view_only:
            return
        btn = event.button()
        if btn == Qt.MouseButton.LeftButton:
            self._button_mask &= ~0x01
        elif btn == Qt.MouseButton.MiddleButton:
            self._button_mask &= ~0x02
        elif btn == Qt.MouseButton.RightButton:
            self._button_mask &= ~0x04
        rx, ry = self._map_pos(int(event.position().x()), int(event.position().y()))
        self.pointer_event.emit(rx, ry, self._button_mask)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._view_only:
            return
        rx, ry = self._map_pos(int(event.position().x()), int(event.position().y()))
        self.pointer_event.emit(rx, ry, self._button_mask)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self._view_only:
            return
        rx, ry  = self._map_pos(
            int(event.position().x()), int(event.position().y())
        )
        delta = event.angleDelta().y()
        btn   = 0x08 if delta > 0 else 0x10   # button 4 = up, 5 = down
        self.pointer_event.emit(rx, ry, self._button_mask | btn)
        self.pointer_event.emit(rx, ry, self._button_mask)

    # ------------------------------------------------------------------
    # Keyboard events
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self._view_only or event.isAutoRepeat():
            return
        self.key_pressed.emit(event.key(), event.text())

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if self._view_only or event.isAutoRepeat():
            return
        self.key_released.emit(event.key(), event.text())


# ---------------------------------------------------------------------------
# VNCWidget — public tab widget
# ---------------------------------------------------------------------------

class VNCWidget(QWidget):
    """
    Tab widget that displays a live VNC session.

    Interface matches SplitView so MainWindow can treat it uniformly:
      all_closed, health_changed, status_message signals; shutdown() method.
    """

    all_closed     = pyqtSignal()
    health_changed = pyqtSignal(int, str)   # conn_id, status
    status_message = pyqtSignal(str)

    def __init__(
        self,
        conn: Connection,
        db:   Database,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._conn    = conn
        self._db      = db
        self._thread: Optional[QThread]    = None
        self._worker: Optional[VNCWorker]  = None
        self._closed  = False

        self._build_ui()
        self._start_connection()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Status bar (top)
        bar = QWidget()
        bar.setFixedHeight(32)
        bar.setStyleSheet("background: palette(window); border-bottom: 1px solid palette(mid);")
        bar_lay = QHBoxLayout(bar)
        bar_lay.setContentsMargins(8, 0, 8, 0)
        bar_lay.setSpacing(12)

        self._status_lbl = QLabel("Connecting…")
        self._status_lbl.setStyleSheet("color: palette(mid); font-size: 11px;")
        bar_lay.addWidget(self._status_lbl)

        self._res_lbl = QLabel("")
        self._res_lbl.setStyleSheet("color: palette(mid); font-size: 11px;")
        bar_lay.addWidget(self._res_lbl)

        bar_lay.addStretch()

        self._view_only_lbl = QLabel("👁 View-only")
        self._view_only_lbl.setStyleSheet("color: palette(mid); font-size: 11px;")
        self._view_only_lbl.setVisible(self._conn.vnc_view_only)
        bar_lay.addWidget(self._view_only_lbl)

        btn_disc = QPushButton("Disconnect")
        btn_disc.setFixedHeight(22)
        btn_disc.setStyleSheet("font-size: 11px;")
        btn_disc.clicked.connect(self._on_disconnect_clicked)
        bar_lay.addWidget(btn_disc)

        root.addWidget(bar)

        # Canvas (centre)
        self._canvas = _VNCCanvas(self)
        self._canvas._view_only = self._conn.vnc_view_only
        self._canvas.key_pressed.connect(self._on_key_pressed)
        self._canvas.key_released.connect(self._on_key_released)
        self._canvas.pointer_event.connect(self._on_pointer_event)
        root.addWidget(self._canvas, stretch=1)

        # Reconnect bar (bottom, hidden by default)
        self._reconnect_bar = QWidget()
        self._reconnect_bar.setFixedHeight(36)
        self._reconnect_bar.setStyleSheet(
            "background: #c0392b; color: white;"
        )
        rb_lay = QHBoxLayout(self._reconnect_bar)
        rb_lay.setContentsMargins(12, 0, 12, 0)
        self._err_lbl = QLabel("Disconnected")
        self._err_lbl.setStyleSheet("color: white; font-size: 12px;")
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
        self._status_lbl.setText("Connecting…")

        self._thread = QThread(self)
        self._worker = VNCWorker(self._conn)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.connected.connect(self._on_connected)
        self._worker.frame_updated.connect(self._on_frame_updated)
        self._worker.error.connect(self._on_error)
        self._worker.disconnected.connect(self._on_disconnected)
        self._worker.disconnected.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)

        self._thread.start()

    def shutdown(self) -> None:
        """Called by MainWindow when the tab is closed."""
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

    def _on_connected(self, width: int, height: int) -> None:
        self._canvas.init_framebuffer(width, height)
        self._status_lbl.setText("Connected")
        self._status_lbl.setStyleSheet("color: #2ecc71; font-size: 11px;")
        self._res_lbl.setText(f"{width}×{height}")
        if self._conn.id is not None:
            self.health_changed.emit(self._conn.id, "connected")
        self.status_message.emit(
            f"VNC connected to {self._conn.host} ({width}×{height})"
        )
        self._canvas.setFocus()

    def _on_frame_updated(self, x: int, y: int, w: int, h: int, data: bytes) -> None:
        self._canvas.apply_frame(x, y, w, h, data)

    def _on_error(self, msg: str) -> None:
        if self._closed:
            return
        self._err_lbl.setText(f"Error: {msg}")
        self._reconnect_bar.setVisible(True)
        self._status_lbl.setText("Error")
        self._status_lbl.setStyleSheet("color: #e74c3c; font-size: 11px;")
        if self._conn.id is not None:
            self.health_changed.emit(self._conn.id, "error")

    def _on_disconnected(self, msg: str) -> None:
        if self._closed:
            return
        self._err_lbl.setText(msg or "Disconnected")
        self._reconnect_bar.setVisible(True)
        self._status_lbl.setText("Disconnected")
        self._status_lbl.setStyleSheet("color: palette(mid); font-size: 11px;")
        if self._conn.id is not None:
            self.health_changed.emit(self._conn.id, "disconnected")

    # ------------------------------------------------------------------
    # Input forwarding
    # ------------------------------------------------------------------

    def _on_key_pressed(self, qt_key: int, text: str) -> None:
        if self._worker:
            self._worker.send_key(qt_key_to_keysym(qt_key, text), True)

    def _on_key_released(self, qt_key: int, text: str) -> None:
        if self._worker:
            self._worker.send_key(qt_key_to_keysym(qt_key, text), False)

    def _on_pointer_event(self, x: int, y: int, button_mask: int) -> None:
        if self._worker:
            self._worker.send_pointer(x, y, button_mask)

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
