"""Cmd+P quick command palette — fuzzy search over connections and actions."""

from __future__ import annotations

import sys

from PyQt6.QtCore import QEvent, QSize, QTimer, Qt
from PyQt6.QtGui import QColor, QKeyEvent, QPainter, QPalette
from PyQt6.QtWidgets import (
    QApplication, QDialog, QLineEdit, QListWidget, QListWidgetItem,
    QStyledItemDelegate, QStyleOptionViewItem, QVBoxLayout, QWidget,
)

_LINUX = sys.platform.startswith("linux")


# ── Roles stored on each QListWidgetItem ──────────────────────────────────────
_ROLE_CB       = Qt.ItemDataRole.UserRole        # callable
_ROLE_SUBTITLE = Qt.ItemDataRole.UserRole + 1    # str


# ── Fuzzy matching ─────────────────────────────────────────────────────────────

def _fuzzy_match(query: str, text: str) -> bool:
    """Return True if every word in *query* appears as a substring of *text*."""
    t = text.lower()
    return all(w in t for w in query.lower().split())


# ── Custom item delegate (label on left, subtitle on right in dim grey) ────────

class _PaletteDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        painter.save()

        selected = bool(option.state & option.state.State_Selected)  # type: ignore[attr-defined]
        bg = QColor("#094771") if selected else QColor(0, 0, 0, 0)
        painter.fillRect(option.rect, bg)

        label    = index.data(Qt.ItemDataRole.DisplayRole) or ""
        subtitle = index.data(_ROLE_SUBTITLE) or ""

        rect = option.rect.adjusted(16, 0, -16, 0)

        # Label (left-aligned)
        fg = QColor("#ffffff") if selected else QColor("#d4d4d4")
        painter.setPen(fg)
        label_rect = rect
        if subtitle:
            # Reserve space on the right for subtitle
            fm = painter.fontMetrics()
            sub_w = fm.horizontalAdvance(subtitle) + 8
            label_rect = rect.adjusted(0, 0, -sub_w, 0)
        painter.drawText(
            label_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            label,
        )

        # Subtitle (right-aligned, dim)
        if subtitle:
            painter.setPen(QColor("#888888"))
            painter.drawText(
                rect,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                subtitle,
            )

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        return QSize(0, 36)


# ── Command palette dialog ─────────────────────────────────────────────────────

class CommandPalette(QDialog):
    """
    VSCode-style command palette.

    Parameters
    ----------
    items:
        List of ``(label, subtitle, callback)`` tuples.
        *callback* is called with no arguments when the user activates the item.
    parent:
        Parent widget; dialog is centered above it.
    """

    def __init__(
        self,
        items: list[tuple[str, str, object]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            parent,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog,
        )
        self._items = items
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._build_ui()
        self._populate("")
        self._position_near_parent(parent)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.setStyleSheet("""
            CommandPalette {
                background: #1f1f1f;
                border: 1px solid #555555;
                border-radius: 8px;
            }
        """)
        self.setFixedWidth(600)

        # Search input
        self._input = QLineEdit()
        self._input.setPlaceholderText("Search connections and commands…")
        self._input.setStyleSheet("""
            QLineEdit {
                background: #3c3c3c;
                color: #d4d4d4;
                border: none;
                border-bottom: 1px solid #454545;
                padding: 12px 16px;
                font-size: 14px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }
        """)
        self._input.textChanged.connect(self._on_query)
        self._input.installEventFilter(self)
        layout.addWidget(self._input)

        # Results list
        self._list = QListWidget()
        self._list.setItemDelegate(_PaletteDelegate(self._list))
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setStyleSheet("""
            QListWidget {
                background: #1f1f1f;
                color: #d4d4d4;
                border: none;
                outline: none;
                font-size: 13px;
            }
            QListWidget::item {
                border-bottom: 1px solid #2d2d2d;
            }
        """)
        self._list.itemActivated.connect(self._activate_item)
        layout.addWidget(self._list)

    def _position_near_parent(self, parent: QWidget | None) -> None:
        """Place the palette at the top-centre of the parent window."""
        if not parent:
            # Fallback: screen centre
            screen = QApplication.primaryScreen()
            if screen:
                sg = screen.availableGeometry()
                self.move(sg.center().x() - self.width() // 2, sg.y() + 80)
            return
        pr = parent.geometry()
        x = pr.x() + (pr.width() - self.width()) // 2
        y = pr.y() + 60
        self.move(x, y)

    # ------------------------------------------------------------------
    # Populate / filter
    # ------------------------------------------------------------------

    def _populate(self, query: str) -> None:
        self._list.clear()
        for label, subtitle, cb in self._items:
            if query and not _fuzzy_match(query, f"{label} {subtitle}"):
                continue
            item = QListWidgetItem(label)
            item.setData(_ROLE_CB, cb)
            item.setData(_ROLE_SUBTITLE, subtitle)
            self._list.addItem(item)
        if self._list.count():
            self._list.setCurrentRow(0)
        # Resize list to fit (max 12 items)
        visible = min(self._list.count(), 12)
        self._list.setFixedHeight(visible * 36 + 4)
        self.adjustSize()

    def _on_query(self, text: str) -> None:
        self._populate(text)

    # ------------------------------------------------------------------
    # Activation
    # ------------------------------------------------------------------

    def _activate_item(self, item: QListWidgetItem) -> None:
        cb = item.data(_ROLE_CB)
        self.accept()
        # Defer the callback so the Enter keypress that triggered activation is
        # fully consumed before any new widget receives focus or input.
        if callable(cb):
            QTimer.singleShot(0, cb)

    # ------------------------------------------------------------------
    # Keyboard handling: arrows + Enter in the search box
    # ------------------------------------------------------------------

    def eventFilter(self, obj: object, event: object) -> bool:
        if obj is self._input and event.type() == QEvent.Type.KeyPress:  # type: ignore[union-attr]
            key = event.key()  # type: ignore[union-attr]
            n   = self._list.count()
            row = self._list.currentRow()
            if key == Qt.Key.Key_Down:
                self._list.setCurrentRow(min(row + 1, n - 1))
                return True
            if key == Qt.Key.Key_Up:
                self._list.setCurrentRow(max(row - 1, 0))
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                item = self._list.currentItem()
                if item:
                    self._activate_item(item)
                return True
            if key == Qt.Key.Key_Escape:
                self.reject()
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)
