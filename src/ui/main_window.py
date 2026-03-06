"""Main application window."""

from __future__ import annotations

import json
import sys

_LINUX = sys.platform.startswith("linux")


def _ico(emoji: str, text: str) -> str:
    return text if _LINUX else emoji

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QVBoxLayout, QToolBar,
    QStatusBar, QMenuBar, QMenu, QMessageBox, QApplication,
    QLineEdit, QLabel, QComboBox, QPushButton, QHBoxLayout,
    QSizePolicy, QTabWidget, QTabBar, QSystemTrayIcon,
)
from PyQt6.QtGui import QAction, QColor, QKeySequence, QFont, QIcon, QPixmap, QPainter
from PyQt6.QtCore import Qt, QSize, QRect, pyqtSignal

from src.storage.database import Database
from src.models.connection import Connection


# ── Detachable tab bar ────────────────────────────────────────────────────────

class _DetachableTabBar(QTabBar):
    """QTabBar that adds a right-click 'Open in New Window' context menu."""

    detach_requested = pyqtSignal(int)   # tab index to detach

    def contextMenuEvent(self, event) -> None:
        idx = self.tabAt(event.pos())
        if idx <= 0:          # 0 = Home tab (permanent), -1 = empty area
            return
        menu = QMenu(self)
        act = QAction("Open in New Window", self)
        act.triggered.connect(lambda: self.detach_requested.emit(idx))
        menu.addAction(act)
        menu.exec(event.globalPos())


# ── Detached window ───────────────────────────────────────────────────────────

class _DetachedWindow(QMainWindow):
    """Standalone window that hosts a detached SplitView (or any widget)."""

    def __init__(self, widget: QWidget, title: str,
                 registry: list) -> None:
        super().__init__()
        self.setWindowTitle(title)
        self.resize(900, 620)
        self._registry = registry
        self.setCentralWidget(widget)
        registry.append(self)

    def closeEvent(self, event) -> None:
        w = self.centralWidget()
        if hasattr(w, "shutdown"):
            w.shutdown()
        if self in self._registry:
            self._registry.remove(self)
        super().closeEvent(event)


# ── Main window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    """Top-level application window (Remmina-style split layout)."""

    def __init__(self, db: Database) -> None:
        super().__init__()
        self.db = db
        self._detached_windows: list[_DetachedWindow] = []
        self._fullscreen_active = False

        self.setWindowTitle("RemminaMac")
        self.setMinimumSize(960, 600)
        self.resize(1200, 720)

        self._build_menu_bar()
        self._build_toolbar()
        self._build_central()
        self._build_status_bar()
        self._setup_tray()

        # Restore window geometry
        geom = db.get_pref("window_geometry")
        if geom:
            self.restoreGeometry(bytes.fromhex(geom))

        # Apply saved terminal theme
        self._apply_terminal_theme_from_prefs()

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

        act_keygen = QAction("🔑 &Generate SSH Key…" if not _LINUX else "&Generate SSH Key…", self)
        if _LINUX:
            act_keygen.setIcon(QIcon.fromTheme("dialog-password"))
        act_keygen.triggered.connect(self._on_generate_key)
        file_menu.addAction(act_keygen)

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

        view_menu.addSeparator()

        self._act_fullscreen = QAction("&Fullscreen", self)
        self._act_fullscreen.setShortcut(QKeySequence("Ctrl+Return"))  # Cmd+Enter on macOS
        self._act_fullscreen.setCheckable(True)
        self._act_fullscreen.triggered.connect(self._on_toggle_fullscreen)
        view_menu.addAction(self._act_fullscreen)

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
        self._toolbar = tb  # kept for fullscreen toggle

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

        # Broadcast toggle (📡 is emoji → use network-wireless theme icon on Linux)
        self._btn_broadcast = QPushButton("" if _LINUX else "📡")
        self._btn_broadcast.setToolTip("Broadcast input to all terminal panes (off)")
        self._btn_broadcast.setCheckable(True)
        self._btn_broadcast.setFixedSize(28, 28)
        self._btn_broadcast.setStyleSheet(
            "QPushButton{background:transparent;border:none;font-size:16px;color:#888;}"
            "QPushButton:checked{color:#e5c07b;}"
            "QPushButton:hover{color:#fff;}"
        )
        if _LINUX:
            _brd_icon = QIcon.fromTheme("network-wireless")
            if not _brd_icon.isNull():
                self._btn_broadcast.setIcon(_brd_icon)
                self._btn_broadcast.setIconSize(QSize(16, 16))
            else:
                self._btn_broadcast.setText("~")
        self._btn_broadcast.toggled.connect(self._on_broadcast_toggled)
        tb.addWidget(self._btn_broadcast)
        self._broadcast_active = False

        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search connections…")
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

        # Right panel: tab widget with detachable tab bar
        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.setMovable(True)
        _tab_bar = _DetachableTabBar()
        _tab_bar.detach_requested.connect(self._on_detach_tab)
        self._tabs.setTabBar(_tab_bar)
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

        # Update status bar when switching tabs
        self._tabs.currentChanged.connect(self._on_tab_changed)

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
        from src.ui.split_view import SplitView

        # If a tab for this connection is already open, just switch to it
        if conn.id is not None:
            for i in range(1, self._tabs.count()):
                w = self._tabs.widget(i)
                if isinstance(w, SplitView) and w.matches_conn(conn):
                    self._tabs.setCurrentIndex(i)
                    return

        view = SplitView(conn, db=self.db, parent=self)
        view.status_message.connect(self.set_status)
        view.health_changed.connect(self._tree.set_health)
        view.all_closed.connect(lambda v=view: self._on_split_view_closed(v))

        tab_icon = QIcon.fromTheme("utilities-terminal") if _LINUX else QIcon()
        idx = self._tabs.addTab(view, tab_icon, f"{'🔑 ' if not _LINUX else ''}{conn.display_name()}")
        if conn.color:
            self._tabs.tabBar().setTabTextColor(idx, QColor(conn.color))
        self._tabs.setCurrentIndex(idx)
        self._track_recent(conn)
        self.set_status(f"Connecting to {conn.connection_string()}…")
        if hasattr(self, "_tray"):
            self._refresh_tray_menu()
        if hasattr(self, "_broadcast_active") and self._broadcast_active:
            self._rewire_broadcast()

    def _on_split_view_closed(self, view) -> None:
        """Remove the tab when the last pane in a SplitView closes cleanly."""
        idx = self._tabs.indexOf(view)
        if idx >= 0:
            self._tabs.removeTab(idx)
            view.deleteLater()
        self.set_status("Session closed.")

    def _on_tab_close_requested(self, index: int) -> None:
        if index == 0:
            return  # home tab is permanent
        widget = self._tabs.widget(index)
        if hasattr(widget, "shutdown"):
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
        self._update_home_tab(DetailWidget(conn, self), f"{'📋 ' if not _LINUX else ''}{conn.display_name()}")

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

    def _on_tab_changed(self, index: int) -> None:
        """Update the status bar to show the active connection's address."""
        if index == 0:
            self.set_status("Ready")
            return
        w = self._tabs.widget(index)
        if hasattr(w, "conn_info"):
            self.set_status(f"Connected to {w.conn_info}")

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
            self._update_home_tab(DetailWidget(dlg.saved_connection, self), f"{_ico('📋 ', '')}{dlg.saved_connection.display_name()}")
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

    def _on_generate_key(self) -> None:
        from src.ui.key_gen_dialog import KeyGenerationDialog
        KeyGenerationDialog(self).exec()

    def _on_quick_connect_focus(self) -> None:
        self._qc_host.setFocus()
        self._qc_host.selectAll()

    def _on_search(self, text: str) -> None:
        self._tree.filter(text)

    def _on_toggle_tree(self, checked: bool) -> None:
        self._tree.setVisible(checked)

    def _on_preferences(self) -> None:
        from src.ui.preferences_dialog import PreferencesDialog
        dlg = PreferencesDialog(self.db, self)
        if dlg.exec():
            self._apply_terminal_theme_from_prefs()
            self._refresh_icons()

    def _refresh_icons(self) -> None:
        """
        Re-apply freedesktop theme icons to all icon-bearing widgets after
        the user has changed the icon theme in Preferences.

        Covers: broadcast toolbar button, connection tree, and all open
        terminal panes (via TerminalWidget.refresh_icons()).
        Has no effect on non-Linux platforms.
        """
        if not _LINUX:
            return
        # Broadcast button
        brd_icon = QIcon.fromTheme("network-wireless")
        if not brd_icon.isNull():
            self._btn_broadcast.setIcon(brd_icon)
            self._btn_broadcast.setIconSize(QSize(16, 16))
            self._btn_broadcast.setText("")
        # Connection tree — reload() rebuilds all items with fresh icons
        self._tree.reload()
        # All open terminal panes
        from src.ui.split_view import SplitView
        for i in range(1, self._tabs.count()):
            w = self._tabs.widget(i)
            if isinstance(w, SplitView):
                for t in w.get_terminals():
                    t.refresh_icons()
        # Detached windows
        for win in self._detached_windows:
            inner = win.centralWidget()
            if isinstance(inner, SplitView):
                for t in inner.get_terminals():
                    t.refresh_icons()

    def _apply_terminal_theme_from_prefs(self) -> None:
        """Load the saved terminal theme pref and apply it to all open terminals."""
        from src.ui.themes import get_theme, theme_names
        from src.ui.terminal_widget import apply_terminal_theme
        name = self.db.get_pref("terminal_theme", theme_names()[0])
        theme = get_theme(name)
        apply_terminal_theme(theme)
        # Refresh any already-open terminal panes
        from src.ui.split_view import SplitView
        for i in range(1, self._tabs.count()):
            w = self._tabs.widget(i)
            if isinstance(w, SplitView):
                for t in w.get_terminals():
                    t._output.refresh_theme()

    # ── Broadcast input ───────────────────────────────────────────────────────

    def _on_broadcast_toggled(self, active: bool) -> None:
        """Enable/disable broadcast: route key_input from active pane to all others."""
        self._broadcast_active = active
        tip = "Broadcast input to all terminal panes (ON)" if active else \
              "Broadcast input to all terminal panes (off)"
        self._btn_broadcast.setToolTip(tip)
        self.set_status("Broadcast ON — keystrokes sent to all panes." if active
                        else "Broadcast OFF.")
        self._rewire_broadcast()

    def _rewire_broadcast(self) -> None:
        """Connect/disconnect key_input → send_data across all open panes."""
        from src.ui.split_view import SplitView

        # Collect every terminal currently open in tabs + detached windows
        all_terminals: list = []
        for i in range(1, self._tabs.count()):
            w = self._tabs.widget(i)
            if isinstance(w, SplitView):
                all_terminals.extend(w.get_terminals())
        for win in self._detached_windows:
            inner = win.centralWidget()
            if isinstance(inner, SplitView):
                all_terminals.extend(inner.get_terminals())

        # Always disconnect first to avoid duplicate connections
        for t in all_terminals:
            try:
                t.key_input.disconnect()
            except TypeError:
                pass  # no connections yet

        if not self._broadcast_active:
            return

        # Re-wire: each terminal broadcasts to all *other* terminals
        for src in all_terminals:
            for dst in all_terminals:
                if dst is not src:
                    src.key_input.connect(dst.send_data)

    def _on_about(self) -> None:
        QMessageBox.about(
            self, "About RemminaMac",
            "<b>RemminaMac 0.1.0</b><br><br>"
            "A Remmina-inspired SSH connection manager for macOS.<br><br>"
            "Built with Python, PyQt6, and paramiko.",
        )

    # ------------------------------------------------------------------
    # Fullscreen
    # ------------------------------------------------------------------

    def _on_toggle_fullscreen(self, checked: bool) -> None:
        """Cmd+Enter — toggle fullscreen: hide/show toolbar, tree, and status bar."""
        self._fullscreen_active = checked
        self._act_fullscreen.setChecked(checked)
        if checked:
            self._toolbar.hide()
            self._splitter.widget(0).hide()   # connection tree
            self.statusBar().hide()
            self.showFullScreen()
        else:
            self._toolbar.show()
            if self._act_toggle_tree.isChecked():
                self._splitter.widget(0).show()
            self.statusBar().show()
            self.showNormal()

    # ------------------------------------------------------------------
    # macOS tray icon
    # ------------------------------------------------------------------

    @staticmethod
    def _make_tray_icon() -> QIcon:
        """Create a 22×22 '>_' terminal icon for the system tray."""
        px = QPixmap(22, 22)
        px.fill(Qt.GlobalColor.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor("#1e1e1e"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(1, 1, 20, 20, 4, 4)
        p.setPen(QColor("#98c379"))
        f = QFont("Menlo", 8)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRect(0, 0, 22, 22), Qt.AlignmentFlag.AlignCenter, ">_")
        p.end()
        return QIcon(px)

    def _setup_tray(self) -> None:
        """Create and show the macOS menu-bar / system-tray icon."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray = QSystemTrayIcon(self._make_tray_icon(), self)
        self._tray.setToolTip("RemminaMac")
        self._tray.activated.connect(self._on_tray_activated)
        self._tray_menu = QMenu()
        self._tray.setContextMenu(self._tray_menu)
        self._refresh_tray_menu()
        self._tray.show()

    def _refresh_tray_menu(self) -> None:
        """Rebuild the tray context menu (called on show and after connection changes)."""
        m = self._tray_menu
        m.clear()

        act_show = QAction("Show RemminaMac", self)
        act_show.triggered.connect(self._bring_to_front)
        m.addAction(act_show)

        m.addSeparator()

        # Quick connect field via dedicated action
        act_qc = QAction("Quick Connect…", self)
        act_qc.triggered.connect(self._on_tray_quick_connect)
        m.addAction(act_qc)

        # Recent connections submenu
        raw = self.db.get_pref("recent_connections")
        recent_ids: list[int] = json.loads(raw) if raw else []
        if recent_ids:
            recent_menu = m.addMenu("Recent Connections")
            all_conns = {c.id: c for c in self.db.all_connections()}
            for cid in recent_ids:
                conn = all_conns.get(cid)
                if conn:
                    act = QAction(conn.display_name(), self)
                    act.triggered.connect(
                        lambda checked, c=conn: (self._bring_to_front(), self._open_terminal(c))
                    )
                    recent_menu.addAction(act)

        m.addSeparator()
        act_quit = QAction("Quit RemminaMac", self)
        act_quit.triggered.connect(QApplication.quit)
        m.addAction(act_quit)

    def _bring_to_front(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self._bring_to_front()
        elif reason == QSystemTrayIcon.ActivationReason.Context:
            self._refresh_tray_menu()

    def _on_tray_quick_connect(self) -> None:
        self._bring_to_front()
        self._qc_host.setFocus()
        self._qc_host.selectAll()

    # ------------------------------------------------------------------
    # Detachable tabs
    # ------------------------------------------------------------------

    def _on_detach_tab(self, index: int) -> None:
        """Pop a tab out into its own standalone window."""
        if index <= 0:
            return
        widget = self._tabs.widget(index)
        label  = self._tabs.tabText(index).strip()
        if not widget:
            return
        self._tabs.removeTab(index)
        widget.setParent(None)  # type: ignore[arg-type]
        _DetachedWindow(widget, f"RemminaMac — {label}", self._detached_windows)

    # ------------------------------------------------------------------
    # Close / persist state
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        for i in range(1, self._tabs.count()):
            w = self._tabs.widget(i)
            if hasattr(w, "shutdown"):
                w.shutdown()
        for win in list(self._detached_windows):
            win.close()
        if hasattr(self, "_tray"):
            self._tray.hide()
        self.db.set_pref("window_geometry", self.saveGeometry().toHex().data().decode())
        super().closeEvent(event)
