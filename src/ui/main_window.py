"""Main application window."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QVBoxLayout, QToolBar,
    QStatusBar, QMenuBar, QMenu, QMessageBox, QApplication,
    QLineEdit, QLabel, QComboBox, QPushButton, QHBoxLayout,
    QSizePolicy,
)
from PyQt6.QtGui import QAction, QKeySequence, QFont, QIcon
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
    # Central widget (splitter)
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

        # Right panel: starts as welcome screen
        self._welcome = WelcomeWidget(self)
        self._right_widget: QWidget = self._welcome
        self._splitter.addWidget(self._right_widget)

        self._splitter.setSizes([260, 940])
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)

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
    # Right-panel management
    # ------------------------------------------------------------------

    def _replace_right(self, widget: QWidget) -> None:
        """Swap the right panel widget."""
        old = self._splitter.widget(1)
        if old is widget:
            return
        sizes = self._splitter.sizes()
        if old is not None:
            old.setParent(None)  # type: ignore[arg-type]
            old.deleteLater()
        self._splitter.addWidget(widget)
        self._splitter.setSizes(sizes)
        self._right_widget = widget

    def _show_terminal(self, conn: Connection) -> None:
        from src.ui.terminal_widget import TerminalWidget
        terminal = TerminalWidget(conn, self)
        terminal.status_message.connect(self.set_status)
        terminal.disconnected.connect(lambda msg: self.set_status(msg))
        self._replace_right(terminal)
        terminal.start_connection()

    def _show_welcome(self) -> None:
        from src.ui.welcome_widget import WelcomeWidget
        self._replace_right(WelcomeWidget(self))

    def _show_detail(self, conn: Connection) -> None:
        from src.ui.welcome_widget import DetailWidget
        self._replace_right(DetailWidget(conn, self))

    # ------------------------------------------------------------------
    # Slot: tree signals
    # ------------------------------------------------------------------

    def _on_connection_selected(self, conn: Connection) -> None:
        self._act_edit_conn.setEnabled(True)
        self._act_del_conn.setEnabled(True)
        self._btn_edit.setEnabled(True)
        self._btn_del.setEnabled(True)
        self._show_detail(conn)

    def _on_connection_activated(self, conn: Connection) -> None:
        """Double-click or Enter — open a terminal."""
        self._show_terminal(conn)
        self.set_status(f"Connecting to {conn.connection_string()}…")

    def _on_selection_cleared(self) -> None:
        self._act_edit_conn.setEnabled(False)
        self._act_del_conn.setEnabled(False)
        self._btn_edit.setEnabled(False)
        self._btn_del.setEnabled(False)
        self._show_welcome()

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
            self._show_detail(dlg.saved_connection)
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
            self._show_welcome()
            self._on_selection_cleared()
            self.set_status(f"Connection '{conn.display_name()}' deleted.")

    def _on_quick_connect(self) -> None:
        text = self._qc_host.text().strip()
        if not text:
            self._qc_host.setFocus()
            return
        conn = self._parse_quick_connect(text)
        self._show_terminal(conn)
        self.set_status(f"Quick connecting to {conn.connection_string()}…")

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
        self.db.set_pref("window_geometry", self.saveGeometry().toHex().data().decode())
        super().closeEvent(event)
