"""Main application window."""

from __future__ import annotations

import json

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QVBoxLayout, QToolBar,
    QStatusBar, QMenuBar, QMenu, QMessageBox, QApplication,
    QLineEdit, QLabel, QComboBox, QPushButton, QHBoxLayout,
    QSizePolicy, QTabWidget, QTabBar,
)
from PyQt6.QtGui import QAction, QColor, QKeySequence, QFont, QIcon
from PyQt6.QtCore import Qt, QSize

from src.storage.database import Database
from src.models.connection import Connection


class MainWindow(QMainWindow):
    """Top-level application window (Remmina-style split layout)."""

    def __init__(self, db: Database) -> None:
        super().__init__()
        self.db = db

        self.setWindowTitle("RemminaMac")
        self.setMinimumSize(960, 600)
        self.resize(1200, 720)

        self._build_menu_bar()
        self._build_toolbar()
        self._build_central()
        self._build_status_bar()

        # Restore window geometry
        geom = db.get_pref("window_geometry")
        if geom:
            self.restoreGeometry(bytes.fromhex(geom))

    # ------------------------------------------------------------------
    # Menu bar
    # ------------------------------------------------------------------

    def _build_menu_bar(self) -> None:
        mb = self.menuBar()

        # File
        file_menu: QMenu = mb.addMenu("&File")

        act_new = QAction("&New Connection…", self)
        act_new.setShortcut(QKeySequence("Ctrl+N"))
        act_new.triggered.connect(self._on_new_connection)
        file_menu.addAction(act_new)

        act_quick = QAction("&Quick Connect…", self)
        act_quick.setShortcut(QKeySequence("Ctrl+Shift+Q"))
        act_quick.triggered.connect(self._on_quick_connect_focus)
        file_menu.addAction(act_quick)

        act_import = QAction("&Import from ~/.ssh/config…", self)
        act_import.triggered.connect(self._on_import_ssh_config)
        file_menu.addAction(act_import)

        file_menu.addSeparator()

        act_quit = QAction("&Quit", self)
        act_quit.setShortcut(QKeySequence("Ctrl+Q"))
        act_quit.triggered.connect(QApplication.quit)
        file_menu.addAction(act_quit)

        # Edit
        edit_menu: QMenu = mb.addMenu("&Edit")

        self._act_edit_conn = QAction("&Edit Connection…", self)
        self._act_edit_conn.setShortcut(QKeySequence("Ctrl+E"))
        self._act_edit_conn.setEnabled(False)
        self._act_edit_conn.triggered.connect(self._on_edit_connection)
        edit_menu.addAction(self._act_edit_conn)

        self._act_del_conn = QAction("&Delete Connection", self)
        self._act_del_conn.setShortcut(QKeySequence("Ctrl+Backspace"))
        self._act_del_conn.setEnabled(False)
        self._act_del_conn.triggered.connect(self._on_delete_connection)
        edit_menu.addAction(self._act_del_conn)

        edit_menu.addSeparator()

        act_prefs = QAction("&Preferences…", self)
        act_prefs.setShortcut(QKeySequence("Ctrl+,"))
        act_prefs.triggered.connect(self._on_preferences)
        edit_menu.addAction(act_prefs)

        # View
        view_menu: QMenu = mb.addMenu("&View")

        self._act_toggle_tree = QAction("&Connection List", self)
        self._act_toggle_tree.setCheckable(True)
        self._act_toggle_tree.setChecked(True)
        self._act_toggle_tree.setShortcut(QKeySequence("Ctrl+Shift+L"))
        self._act_toggle_tree.triggered.connect(self._on_toggle_tree)
        view_menu.addAction(self._act_toggle_tree)

        # Window
        win_menu: QMenu = mb.addMenu("&Window")

        act_close_tab = QAction("Close Tab", self)
        act_close_tab.setShortcut(QKeySequence("Ctrl+W"))
        act_close_tab.triggered.connect(self._on_close_current_tab)
        win_menu.addAction(act_close_tab)

        win_menu.addSeparator()

        # Cmd+1–9: switch to tab by position (invisible — added to window only)
        for i in range(1, 10):
            act = QAction(f"Select Tab {i}", self)
            act.setShortcut(QKeySequence(f"Ctrl+{i}"))
            act.triggered.connect(lambda checked, n=i - 1: self._tabs.setCurrentIndex(n))
            act.setVisible(False)   # keyboard-only; not shown in menu
            win_menu.addAction(act)

        # Help
        help_menu: QMenu = mb.addMenu("&Help")
        act_about = QAction("&About RemminaMac", self)
        act_about.triggered.connect(self._on_about)
        help_menu.addAction(act_about)

    # ------------------------------------------------------------------
    # Toolbar (quick connect)
    # ------------------------------------------------------------------

    def _build_toolbar(self) -> None:
        tb = QToolBar("Main Toolbar")
        tb.setMovable(False)
        tb.setIconSize(QSize(18, 18))
        tb.setStyleSheet("QToolBar { spacing: 6px; padding: 4px 8px; }")
        self.addToolBar(tb)

        # New / Edit / Delete buttons
        btn_new = QPushButton("＋ New")
        btn_new.setToolTip("New Connection (Ctrl+N)")
        btn_new.clicked.connect(self._on_new_connection)
        tb.addWidget(btn_new)

        self._btn_edit = QPushButton("✎ Edit")
        self._btn_edit.setToolTip("Edit selected connection (Ctrl+E)")
        self._btn_edit.setEnabled(False)
        self._btn_edit.clicked.connect(self._on_edit_connection)
        tb.addWidget(self._btn_edit)

        self._btn_del = QPushButton("⌫ Delete")
        self._btn_del.setToolTip("Delete selected connection")
        self._btn_del.setEnabled(False)
        self._btn_del.clicked.connect(self._on_delete_connection)
        tb.addWidget(self._btn_del)

        # Separator
        sep = QWidget()
        sep.setFixedWidth(12)
        tb.addWidget(sep)

        # Quick connect section
        lbl = QLabel("Quick Connect:")
        lbl.setStyleSheet("color: palette(text);")
        tb.addWidget(lbl)

        self._qc_host = QLineEdit()
        self._qc_host.setPlaceholderText("user@host[:port]")
        self._qc_host.setFixedWidth(220)
        self._qc_host.returnPressed.connect(self._on_quick_connect)
        tb.addWidget(self._qc_host)

        btn_go = QPushButton("⚡ Connect")
        btn_go.setToolTip("Open quick SSH connection")
        btn_go.clicked.connect(self._on_quick_connect)
        tb.addWidget(btn_go)

        # Spacer to right-align remaining items
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)

        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("🔍  Search connections…")
        self._search_box.setFixedWidth(200)
        self._search_box.setClearButtonEnabled(True)
        self._search_box.textChanged.connect(self._on_search)
        tb.addWidget(self._search_box)

    # ------------------------------------------------------------------
    # Central widget (splitter + tab panel)
    # ------------------------------------------------------------------

    def _build_central(self) -> None:
        from src.ui.connection_tree import ConnectionTree
        from src.ui.welcome_widget import WelcomeWidget

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(1)
        self.setCentralWidget(self._splitter)

        # Left panel: connection tree
        self._tree = ConnectionTree(self.db, self)
        self._tree.setMinimumWidth(220)
        self._splitter.addWidget(self._tree)

        # Right panel: tab widget (home tab + terminal tabs)
        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.setMovable(True)
        self._tabs.tabCloseRequested.connect(self._on_tab_close_requested)
        self._splitter.addWidget(self._tabs)

        self._splitter.setSizes([260, 940])
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)

        # Permanent home tab at index 0 — no close button
        self._tabs.addTab(WelcomeWidget(self.db, self), "Home")
        self._tabs.tabBar().setTabButton(0, QTabBar.ButtonPosition.RightSide, None)

        # Wire tree signals
        self._tree.connection_selected.connect(self._on_connection_selected)
        self._tree.connection_activated.connect(self._on_connection_activated)
        self._tree.selection_cleared.connect(self._on_selection_cleared)

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _build_status_bar(self) -> None:
        sb = QStatusBar()
        self.setStatusBar(sb)
        self._status_label = QLabel("Ready")
        sb.addWidget(self._status_label)

    def set_status(self, msg: str) -> None:
        self._status_label.setText(msg)

    # ------------------------------------------------------------------
    # Tab management
    # ------------------------------------------------------------------

    def _update_home_tab(self, widget: QWidget, label: str = "Home") -> None:
        """Replace the home tab content without touching terminal tabs."""
        was_current = self._tabs.currentIndex() == 0
        old = self._tabs.widget(0)
        self._tabs.removeTab(0)
        if old:
            old.deleteLater()
        self._tabs.insertTab(0, widget, label)
        self._tabs.tabBar().setTabButton(0, QTabBar.ButtonPosition.RightSide, None)
        if was_current:
            self._tabs.setCurrentIndex(0)

    def _open_terminal(self, conn: Connection) -> None:
        """Open a new terminal tab for conn; switch to existing tab if already open."""
        from src.ui.terminal_widget import TerminalWidget

        # If a tab for this connection is already open, just switch to it
        if conn.id is not None:
            for i in range(1, self._tabs.count()):
                w = self._tabs.widget(i)
                if isinstance(w, TerminalWidget) and getattr(w._conn, "id", None) == conn.id:
                    self._tabs.setCurrentIndex(i)
                    return

        terminal = TerminalWidget(conn, db=self.db, parent=self)
        terminal.status_message.connect(self.set_status)
        terminal.disconnected.connect(
            lambda msg, t=terminal: self._on_terminal_disconnected(t, msg)
        )
        idx = self._tabs.addTab(terminal, f"🔑 {conn.display_name()}")
        if conn.color:
            self._tabs.tabBar().setTabTextColor(idx, QColor(conn.color))
        self._tabs.setCurrentIndex(idx)
        terminal.start_connection()
        self._track_recent(conn)
        self.set_status(f"Connecting to {conn.connection_string()}…")

    def _on_terminal_disconnected(self, terminal, msg: str) -> None:
        """Close the tab automatically when a session ends."""
        self.set_status(msg)
        idx = self._tabs.indexOf(terminal)
        if idx >= 0:
            self._tabs.removeTab(idx)
            terminal.shutdown()
            terminal.deleteLater()

    def _on_tab_close_requested(self, index: int) -> None:
        if index == 0:
            return  # home tab is permanent
        from src.ui.terminal_widget import TerminalWidget
        widget = self._tabs.widget(index)
        if isinstance(widget, TerminalWidget):
            widget.shutdown()
        self._tabs.removeTab(index)
        if widget:
            widget.deleteLater()

    def _on_close_current_tab(self) -> None:
        idx = self._tabs.currentIndex()
        if idx > 0:
            self._on_tab_close_requested(idx)

    def _track_recent(self, conn: Connection) -> None:
        """Keep a list of the 5 most-recently opened connection IDs in prefs."""
        if conn.id is None:
            return
        raw = self.db.get_pref("recent_connections")
        ids: list[int] = json.loads(raw) if raw else []
        if conn.id in ids:
            ids.remove(conn.id)
        ids.insert(0, conn.id)
        self.db.set_pref("recent_connections", json.dumps(ids[:5]))

    # ------------------------------------------------------------------
    # Slot: tree signals
    # ------------------------------------------------------------------

    def _on_connection_selected(self, conn: Connection) -> None:
        self._act_edit_conn.setEnabled(True)
        self._act_del_conn.setEnabled(True)
        self._btn_edit.setEnabled(True)
        self._btn_del.setEnabled(True)
        from src.ui.welcome_widget import DetailWidget
        self._update_home_tab(DetailWidget(conn, self), f"📋 {conn.display_name()}")

    def _on_connection_activated(self, conn: Connection) -> None:
        """Double-click or Enter — open a terminal tab."""
        self._open_terminal(conn)

    def _on_selection_cleared(self) -> None:
        self._act_edit_conn.setEnabled(False)
        self._act_del_conn.setEnabled(False)
        self._btn_edit.setEnabled(False)
        self._btn_del.setEnabled(False)
        from src.ui.welcome_widget import WelcomeWidget
        self._update_home_tab(WelcomeWidget(self.db, self), "Home")

    # ------------------------------------------------------------------
    # Slot: toolbar / menu actions
    # ------------------------------------------------------------------

    def _on_new_connection(self) -> None:
        from src.ui.connection_dialog import ConnectionDialog
        dlg = ConnectionDialog(self.db, parent=self)
        if dlg.exec():
            self._tree.reload()
            self.set_status(f"Connection '{dlg.saved_connection.display_name()}' created.")

    def _on_edit_connection(self) -> None:
        conn = self._tree.selected_connection()
        if not conn:
            return
        from src.ui.connection_dialog import ConnectionDialog
        dlg = ConnectionDialog(self.db, connection=conn, parent=self)
        if dlg.exec():
            self._tree.reload()
            from src.ui.welcome_widget import DetailWidget
            self._update_home_tab(DetailWidget(dlg.saved_connection, self), f"📋 {dlg.saved_connection.display_name()}")
            self.set_status(f"Connection '{dlg.saved_connection.display_name()}' updated.")

    def _on_delete_connection(self) -> None:
        conn = self._tree.selected_connection()
        if not conn:
            return
        reply = QMessageBox.question(
            self, "Delete Connection",
            f"Delete connection «{conn.display_name()}»?\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.db.delete_connection(conn.id)
            self._tree.reload()
            self._on_selection_cleared()
            self.set_status(f"Connection '{conn.display_name()}' deleted.")

    def _on_quick_connect(self) -> None:
        text = self._qc_host.text().strip()
        if not text:
            self._qc_host.setFocus()
            return
        conn = self._parse_quick_connect(text)
        self._open_terminal(conn)

    @staticmethod
    def _parse_quick_connect(text: str) -> Connection:
        """Parse 'user@host:port' into a transient Connection."""
        conn = Connection()
        # strip optional ssh:// scheme
        if text.startswith("ssh://"):
            text = text[6:]
        if "@" in text:
            conn.username, rest = text.split("@", 1)
        else:
            rest = text
        if ":" in rest:
            conn.host, port_str = rest.rsplit(":", 1)
            try:
                conn.port = int(port_str)
            except ValueError:
                conn.host = rest
        else:
            conn.host = rest
        conn.name = conn.host
        return conn

    def _on_import_ssh_config(self) -> None:
        from src.ui.ssh_config_import_dialog import SshConfigImportDialog
        dlg = SshConfigImportDialog(self.db, self)
        if dlg.exec():
            self._tree.reload()
            self.set_status("SSH config imported.")

    def _on_quick_connect_focus(self) -> None:
        self._qc_host.setFocus()
        self._qc_host.selectAll()

    def _on_search(self, text: str) -> None:
        self._tree.filter(text)

    def _on_toggle_tree(self, checked: bool) -> None:
        self._tree.setVisible(checked)

    def _on_preferences(self) -> None:
        from src.ui.preferences_dialog import PreferencesDialog
        PreferencesDialog(self.db, self).exec()

    def _on_about(self) -> None:
        QMessageBox.about(
            self, "About RemminaMac",
            "<b>RemminaMac 0.1.0</b><br><br>"
            "A Remmina-inspired SSH connection manager for macOS.<br><br>"
            "Built with Python, PyQt6, and paramiko.",
        )

    # ------------------------------------------------------------------
    # Close / persist state
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        from src.ui.terminal_widget import TerminalWidget
        for i in range(1, self._tabs.count()):
            w = self._tabs.widget(i)
            if isinstance(w, TerminalWidget):
                w.shutdown()
        self.db.set_pref("window_geometry", self.saveGeometry().toHex().data().decode())
        super().closeEvent(event)
