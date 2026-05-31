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

    def __init__(self, db: Database, name: str | None = None) -> None:
        super().__init__()
        self.db = db
        self._detached_windows: list[_DetachedWindow] = []
        self._fullscreen_active = False

        title = f"SSHelf — {name}" if name else "SSHelf"
        self.setWindowTitle(title)
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

        # Apply feature visibility prefs (broadcast button, etc.)
        self._apply_feature_prefs()

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

        act_palette = QAction("&Command Palette…", self)
        act_palette.setShortcut(QKeySequence("Ctrl+P"))
        act_palette.triggered.connect(self._on_command_palette)
        file_menu.addAction(act_palette)

        act_import = QAction("&Import from ~/.ssh/config…", self)
        act_import.triggered.connect(self._on_import_ssh_config)
        file_menu.addAction(act_import)

        act_keygen = QAction("🔑 &Generate SSH Key…" if not _LINUX else "&Generate SSH Key…", self)
        if _LINUX:
            act_keygen.setIcon(QIcon.fromTheme("dialog-password"))
        act_keygen.triggered.connect(self._on_generate_key)
        file_menu.addAction(act_keygen)

        file_menu.addSeparator()

        act_export = QAction("📤 &Export Connections as JSON…" if not _LINUX else "&Export Connections as JSON…", self)
        if _LINUX:
            act_export.setIcon(QIcon.fromTheme("document-save-as"))
        act_export.triggered.connect(self._on_export_connections)
        file_menu.addAction(act_export)

        act_import_json = QAction("📥 &Import Connections from JSON…" if not _LINUX else "&Import Connections from JSON…", self)
        if _LINUX:
            act_import_json.setIcon(QIcon.fromTheme("document-open"))
        act_import_json.triggered.connect(self._on_import_connections)
        file_menu.addAction(act_import_json)

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
        act_about = QAction("&About SSHelf", self)
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
        """Open a new tab for conn; switch to existing tab if already open."""
        from src.ui.split_view import SplitView
        from src.plugins.rdp import RDPWidget
        from src.plugins.vnc import VNCWidget

        # Protocol → view class + tab label prefix + Linux theme icon
        _VIEW = {
            "rdp": (RDPWidget, "🖥 ", "computer"),
            "vnc": (VNCWidget, "🖱 ", "network-wired"),
        }
        ViewClass, icon_prefix, theme_key = _VIEW.get(
            conn.protocol, (SplitView, "🔑 ", "utilities-terminal")
        )

        # If a tab for this connection is already open, just switch to it
        if conn.id is not None:
            for i in range(1, self._tabs.count()):
                w = self._tabs.widget(i)
                if hasattr(w, "matches_conn") and w.matches_conn(conn):
                    self._tabs.setCurrentIndex(i)
                    return

        view = ViewClass(conn, db=self.db, parent=self)
        view.status_message.connect(self.set_status)
        view.health_changed.connect(self._tree.set_health)
        view.all_closed.connect(lambda v=view: self._on_split_view_closed(v))

        tab_icon = QIcon.fromTheme(theme_key) if _LINUX else QIcon()
        label = f"{'' if _LINUX else icon_prefix}{conn.display_name()}"
        idx = self._tabs.addTab(view, tab_icon, label)
        if conn.color:
            self._tabs.tabBar().setTabTextColor(idx, QColor(conn.color))
        self._tabs.setCurrentIndex(idx)
        self._track_recent(conn)
        self.set_status(f"Connecting to {conn.connection_string()}…")
        if hasattr(self, "_tray"):
            self._refresh_tray_menu()
        if (hasattr(self, "_broadcast_active") and self._broadcast_active
                and self.db.get_pref("feature_broadcast", "0") == "1"):
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
        """Parse 'user@host:port' or 'rdp://host:port' into a transient Connection."""
        conn = Connection()
        # Detect protocol from scheme
        for scheme in ("ssh://", "rdp://", "vnc://"):
            if text.lower().startswith(scheme):
                conn.protocol = scheme[:3]
                text = text[len(scheme):]
                break
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

    def _on_command_palette(self) -> None:
        """Open the Cmd+P command palette with connections + app actions."""
        from src.ui.command_palette import CommandPalette

        items: list[tuple[str, str, object]] = []

        # ── Saved connections ──────────────────────────────────────────
        for conn in self.db.all_connections():
            c = conn  # capture
            label = f"{_ico('🔑', '[SSH]')}  {c.display_name()}"
            items.append((label, c.connection_string(), lambda c=c: self._open_terminal(c)))

        # ── App actions ────────────────────────────────────────────────
        items += [
            (f"{_ico('＋', '+')}  New Connection…",      "Ctrl+N",  self._on_new_connection),
            (f"{_ico('✎', 'E')}  Edit Connection…",       "Ctrl+E",  self._on_edit_connection),
            ("⚙  Preferences…",                            "Ctrl+,",  self._on_preferences),
            ("📥  Import ~/.ssh/config…",                  "",         self._on_import_ssh_config),
            (f"{_ico('🔑', 'K')}  Generate SSH Key…",     "",         self._on_generate_key),
            *([("📡  Toggle Broadcast Input", "", lambda: self._btn_broadcast.toggle())]
              if self.db.get_pref("feature_broadcast", "0") == "1" else []),
            ("⬛  Toggle Fullscreen",                       "Ctrl+↩",  lambda: self._on_toggle_fullscreen(
                                                                            not self._fullscreen_active)),
        ]

        palette = CommandPalette(items, parent=self)
        palette.exec()

    def _on_search(self, text: str) -> None:
        self._tree.filter(text)

    def _on_toggle_tree(self, checked: bool) -> None:
        self._tree.setVisible(checked)

    def _on_preferences(self) -> None:
        from src.ui.preferences_dialog import PreferencesDialog
        PreferencesDialog(self.db, self).exec()
        # Re-apply after dialog closes so feature visibility is always up-to-date.
        self._apply_feature_prefs()

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

    def _apply_feature_prefs(self) -> None:
        """Show/hide toolbar features based on saved preference flags."""
        if self.db.get_pref("feature_broadcast", "0") != "1":
            self._btn_broadcast.hide()
        else:
            self._btn_broadcast.show()

    # ── JSON backup / restore ─────────────────────────────────────────────────

    def _on_export_connections(self) -> None:
        """Export all connections to a JSON file (Preferences → File menu)."""
        import datetime
        from pathlib import Path
        from PyQt6.QtWidgets import QFileDialog, QMessageBox

        reply = QMessageBox.question(
            self, "Include passwords?",
            "Include passwords in the export file?\n\n"
            "⚠  Passwords will be saved as plain text in the JSON file.\n"
            "Only do this on a trusted, private machine.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        include_pw = reply == QMessageBox.StandardButton.Yes

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Connections",
            str(Path.home() / "sshelf-connections.json"),
            "JSON files (*.json)",
        )
        if not path:
            return

        conns = self.db.all_connections()

        def _conn_dict(c):
            d = c.to_dict()
            d.pop("id", None)
            d["group"] = d.pop("group_name", "Default")
            if not include_pw:
                d.pop("password", None)
                d.pop("passphrase", None)
            return d

        data = {
            "version": "1.0",
            "app": "sshelf",
            "exported_at": datetime.datetime.now().isoformat(),
            "connections": [_conn_dict(c) for c in conns],
        }
        try:
            Path(path).write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except OSError as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        QMessageBox.information(
            self, "Export complete",
            f"Exported {len(conns)} connection(s) to:\n{path}",
        )

    def _on_import_connections(self) -> None:
        """Import connections from a JSON file previously exported by sshelf."""
        from pathlib import Path
        from PyQt6.QtWidgets import QFileDialog, QMessageBox

        path, _ = QFileDialog.getOpenFileName(
            self, "Import Connections",
            str(Path.home()),
            "JSON files (*.json)",
        )
        if not path:
            return

        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            QMessageBox.critical(self, "Import failed", f"Could not read file:\n{exc}")
            return

        if not isinstance(data, dict) or "connections" not in data:
            QMessageBox.critical(
                self, "Import failed",
                "File does not look like a sshelf export\n"
                "(missing 'connections' key).",
            )
            return

        conns_data = data["connections"]
        if not isinstance(conns_data, list):
            QMessageBox.critical(self, "Import failed", "Invalid format.")
            return

        existing = {(c.name, c.host) for c in self.db.all_connections()}
        new_items = [
            d for d in conns_data
            if isinstance(d, dict) and
               (d.get("name", ""), d.get("host", "")) not in existing
        ]
        skip_count = len(conns_data) - len(new_items)

        msg = f"Found {len(conns_data)} connection(s) in the file.\n"
        if skip_count:
            msg += f"{skip_count} already exist (same name + host) — will be skipped.\n"
        msg += f"\nImport {len(new_items)} new connection(s)?"

        reply = QMessageBox.question(
            self, "Import Connections", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        for d in new_items:
            d.pop("id", None)
            # Support both 'group' (export key) and 'group_name' (DB key)
            if "group" in d and "group_name" not in d:
                d["group_name"] = d.pop("group")
            try:
                conn = Connection.from_dict(d)
                self.db.save_connection(conn)
            except Exception:
                pass  # skip malformed entries silently

        self._tree.reload()
        QMessageBox.information(
            self, "Import complete",
            f"Imported {len(new_items)} connection(s).",
        )

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
            except (TypeError, RuntimeError):
                pass  # no connections yet (PyQt6 raises TypeError or RuntimeError)

        if not self._broadcast_active:
            return

        # Re-wire: each terminal broadcasts to all *other* terminals
        for src in all_terminals:
            for dst in all_terminals:
                if dst is not src:
                    src.key_input.connect(dst.send_data)

    def _on_about(self) -> None:
        QMessageBox.about(
            self, "About SSHelf",
            "<b>SSHelf 0.1.0</b><br><br>"
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
        self._tray.setToolTip("SSHelf")
        self._tray.activated.connect(self._on_tray_activated)
        self._tray_menu = QMenu()
        self._tray.setContextMenu(self._tray_menu)
        self._refresh_tray_menu()
        self._tray.show()

    def _refresh_tray_menu(self) -> None:
        """Rebuild the tray context menu (called on show and after connection changes)."""
        m = self._tray_menu
        m.clear()

        act_show = QAction("Show SSHelf", self)
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
        act_quit = QAction("Quit SSHelf", self)
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
        _DetachedWindow(widget, f"SSHelf — {label}", self._detached_windows)

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
