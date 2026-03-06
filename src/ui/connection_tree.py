"""Left-panel connection tree widget."""

from __future__ import annotations

import sys
from typing import Optional

_LINUX = sys.platform.startswith("linux")

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem,
    QMenu, QAbstractItemView, QHeaderView,
)
from PyQt6.QtGui import QAction, QFont, QColor, QBrush, QIcon, QPixmap, QPainter
from PyQt6.QtCore import Qt, pyqtSignal, QPoint

from src.storage.database import Database
from src.models.connection import Connection


_GROUP_FLAGS = (
    Qt.ItemFlag.ItemIsEnabled |
    Qt.ItemFlag.ItemIsSelectable |
    Qt.ItemFlag.ItemIsDropEnabled
)

_CONN_FLAGS = (
    Qt.ItemFlag.ItemIsEnabled |
    Qt.ItemFlag.ItemIsSelectable |
    Qt.ItemFlag.ItemIsDragEnabled
)


class ConnectionTree(QWidget):
    """
    Displays all saved connections in a two-level tree:

        ▼ Group Name
              🔑  My Server          192.168.1.1:22
              🔑  Another Host       dev.example.com

    Signals
    -------
    connection_selected(Connection)  — single click / selection change
    connection_activated(Connection) — double-click or Enter key
    selection_cleared()              — no connection selected
    """

    connection_selected = pyqtSignal(object)
    connection_activated = pyqtSignal(object)
    selection_cleared = pyqtSignal()

    def __init__(self, db: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.db = db
        self._filter_text = ""
        self._connections: list[Connection] = []
        self._health: dict[int, str] = {}  # conn_id → "connected"|"error"|"disconnected"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._tree = QTreeWidget()
        self._tree.setColumnCount(2)
        self._tree.setHeaderLabels(["Name", "Host"])
        self._tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.setRootIsDecorated(True)
        self._tree.setUniformRowHeights(True)
        self._tree.setAnimated(True)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        self._tree.itemSelectionChanged.connect(self._on_selection_changed)
        self._tree.itemActivated.connect(self._on_item_activated)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)

        layout.addWidget(self._tree)
        self.reload()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reload(self) -> None:
        """Reload all connections from DB and repopulate the tree."""
        self._connections = self.db.all_connections()
        self._repopulate()

    def filter(self, text: str) -> None:
        """Show only connections whose name/host contains *text*."""
        self._filter_text = text.lower()
        self._repopulate()

    def selected_connection(self) -> Optional[Connection]:
        items = self._tree.selectedItems()
        if not items:
            return None
        return items[0].data(0, Qt.ItemDataRole.UserRole)

    def set_health(self, conn_id: int, status: str) -> None:
        """Update the live health indicator for a connection in the tree.

        status: "connected" → green dot, "error" → red dot, "disconnected" → no dot.
        """
        self._health[conn_id] = status
        # Walk the current tree to find and update the item in-place
        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            group = root.child(i)
            for j in range(group.childCount()):
                item = group.child(j)
                conn = item.data(0, Qt.ItemDataRole.UserRole)
                if conn and conn.id == conn_id:
                    self._apply_health_to_item(item, status)
                    return

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_health_icon(status: str) -> QIcon:
        """Create a small 12×12 filled-circle icon for the given health status."""
        px = QPixmap(12, 12)
        px.fill(Qt.GlobalColor.transparent)
        painter = QPainter(px)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor("#98c379") if status == "connected" else QColor("#e06c75")
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(1, 1, 10, 10)
        painter.end()
        return QIcon(px)

    def _apply_health_to_item(self, item: QTreeWidgetItem, status: str) -> None:
        """Set or clear the health icon on a tree item."""
        if status in ("connected", "error"):
            item.setIcon(0, self._make_health_icon(status))
        else:
            item.setIcon(0, QIcon())   # clear dot when disconnected

    def _repopulate(self) -> None:
        """Clear and rebuild the tree from self._connections."""
        self._tree.blockSignals(True)
        # Remember expanded groups
        expanded: set[str] = set()
        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            if item.isExpanded():
                expanded.add(item.text(0))

        self._tree.clear()

        # Filter
        conns = self._connections
        if self._filter_text:
            conns = [
                c for c in conns
                if self._filter_text in c.display_name().lower()
                or self._filter_text in c.host.lower()
            ]

        # Group items
        groups: dict[str, QTreeWidgetItem] = {}
        for conn in conns:
            group_name = conn.group or "Default"
            if group_name not in groups:
                g_item = QTreeWidgetItem([group_name])
                g_item.setFlags(_GROUP_FLAGS)
                bold = QFont()
                bold.setBold(True)
                g_item.setFont(0, bold)
                g_item.setData(0, Qt.ItemDataRole.UserRole, None)
                self._tree.addTopLevelItem(g_item)
                groups[group_name] = g_item
                if not self._filter_text and group_name in expanded:
                    g_item.setExpanded(True)
                elif self._filter_text:
                    g_item.setExpanded(True)

            c_item = QTreeWidgetItem()
            _prefix = "  " if _LINUX else "  🔑  "
            c_item.setText(0, f"{_prefix}{conn.display_name()}")
            c_item.setText(1, conn.connection_string())
            c_item.setFlags(_CONN_FLAGS)
            c_item.setData(0, Qt.ItemDataRole.UserRole, conn)
            c_item.setToolTip(0, conn.notes or conn.connection_string())

            # Colour dot using the connection's assigned colour
            if conn.color:
                c_item.setForeground(0, QBrush(QColor(conn.color)))

            # Health indicator — restore live dot after repopulate
            if conn.id is not None:
                health = self._health.get(conn.id)
                if health and health != "disconnected":
                    self._apply_health_to_item(c_item, health)

            groups[group_name].addChild(c_item)

        # Expand all groups when filtering; otherwise expand Default
        if not self._filter_text:
            for i in range(self._tree.topLevelItemCount()):
                item = self._tree.topLevelItem(i)
                if item and item.text(0) in expanded:
                    item.setExpanded(True)
            # Auto-expand if only one group
            if self._tree.topLevelItemCount() == 1:
                self._tree.topLevelItem(0).setExpanded(True)
        else:
            for i in range(self._tree.topLevelItemCount()):
                self._tree.topLevelItem(i).setExpanded(True)

        self._tree.blockSignals(False)

    # ------------------------------------------------------------------
    # Signals / events
    # ------------------------------------------------------------------

    def _on_selection_changed(self) -> None:
        conn = self.selected_connection()
        if conn:
            self.connection_selected.emit(conn)
        else:
            # A group header is selected — clear detail panel
            items = self._tree.selectedItems()
            if not items or items[0].data(0, Qt.ItemDataRole.UserRole) is None:
                self.selection_cleared.emit()

    def _on_item_activated(self, item: QTreeWidgetItem, column: int) -> None:
        conn: Optional[Connection] = item.data(0, Qt.ItemDataRole.UserRole)
        if conn:
            self.connection_activated.emit(conn)
        else:
            # Toggle group expand/collapse
            item.setExpanded(not item.isExpanded())

    def _on_context_menu(self, pos: QPoint) -> None:
        item = self._tree.itemAt(pos)
        if not item:
            return
        conn: Optional[Connection] = item.data(0, Qt.ItemDataRole.UserRole)

        menu = QMenu(self)

        if conn:
            act_connect = QAction("Connect" if _LINUX else "⚡  Connect", self)
            act_connect.triggered.connect(lambda: self.connection_activated.emit(conn))
            menu.addAction(act_connect)
            menu.addSeparator()

            act_edit = QAction("✎  Edit…", self)
            act_edit.triggered.connect(lambda: self._edit_connection(conn))
            menu.addAction(act_edit)

            act_dup = QAction("⎘  Duplicate", self)
            act_dup.triggered.connect(lambda: self._duplicate_connection(conn))
            menu.addAction(act_dup)

            menu.addSeparator()

            act_del = QAction("⌫  Delete", self)
            act_del.triggered.connect(lambda: self._delete_connection(conn))
            menu.addAction(act_del)
        else:
            # Group context
            group_name = item.text(0)
            act_add = QAction("＋  New Connection in this Group", self)
            act_add.triggered.connect(lambda: self._new_in_group(group_name))
            menu.addAction(act_add)

        menu.exec(self._tree.mapToGlobal(pos))

    # ------------------------------------------------------------------
    # Context-menu actions
    # ------------------------------------------------------------------

    def _edit_connection(self, conn: Connection) -> None:
        from src.ui.connection_dialog import ConnectionDialog
        parent_window = self.window()
        dlg = ConnectionDialog(self.db, connection=conn, parent=parent_window)
        if dlg.exec():
            self.reload()
            self.connection_selected.emit(dlg.saved_connection)

    def _duplicate_connection(self, conn: Connection) -> None:
        import copy
        dup = copy.deepcopy(conn)
        dup.id = None
        dup.name = f"{conn.name} (copy)" if conn.name else f"{conn.host} (copy)"
        self.db.save_connection(dup)
        self.reload()

    def _delete_connection(self, conn: Connection) -> None:
        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "Delete Connection",
            f"Delete «{conn.display_name()}»?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.db.delete_connection(conn.id)
            self.reload()
            self.selection_cleared.emit()

    def _new_in_group(self, group_name: str) -> None:
        from src.ui.connection_dialog import ConnectionDialog
        conn = Connection(group=group_name)
        dlg = ConnectionDialog(self.db, connection=conn, parent=self.window())
        if dlg.exec():
            self.reload()
