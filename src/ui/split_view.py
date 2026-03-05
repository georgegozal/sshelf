"""SplitView — horizontal split container for multiple TerminalWidget panes."""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSplitter
from PyQt6.QtCore import Qt, pyqtSignal

from src.models.connection import Connection
from src.storage.database import Database


class SplitView(QWidget):
    """
    Tab content widget that holds one or more TerminalWidget panes side by
    side inside a horizontal QSplitter.

    Clicking the ⊞ button on any pane adds a new pane to the right.
    When all panes close cleanly, ``all_closed`` is emitted so MainWindow
    can remove the tab.

    Signals
    -------
    all_closed()            — every pane has disconnected cleanly
    status_message(str)     — forwarded from the most-recently active pane
    health_changed(int,str) — best health status across all panes:
                              "connected" > "error" > "disconnected"
    """

    all_closed     = pyqtSignal()
    status_message = pyqtSignal(str)
    health_changed = pyqtSignal(int, str)

    def __init__(
        self,
        conn: Connection,
        db: Database,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._conn = conn
        self._db   = db
        self._terminals: list = []
        self._pane_health: dict = {}   # terminal → status string

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(self._splitter)

        self._add_pane()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def matches_conn(self, conn: Connection) -> bool:
        """True when this view was opened for *conn* (by saved ID)."""
        return self._conn.id is not None and self._conn.id == conn.id

    def get_terminals(self) -> list:
        """Return a snapshot of the current live TerminalWidget panes."""
        return list(self._terminals)

    def shutdown(self) -> None:
        """Gracefully shut down all panes (called when the tab is force-closed)."""
        for t in list(self._terminals):
            t.shutdown()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _add_pane(self) -> None:
        """Append a new TerminalWidget pane to the right of the splitter."""
        from src.ui.terminal_widget import TerminalWidget

        t = TerminalWidget(self._conn, db=self._db, parent=self)
        t.status_message.connect(self.status_message)
        t.health_changed.connect(
            lambda cid, s, term=t: self._on_pane_health(term, cid, s)
        )
        t.disconnected.connect(
            lambda _msg, term=t: self._on_pane_disconnected(term)
        )
        t.split_requested.connect(self._add_pane)

        self._splitter.addWidget(t)
        self._terminals.append(t)
        self._pane_health[t] = "disconnected"
        t.start_connection()

    def _on_pane_health(self, terminal, conn_id: int, status: str) -> None:
        """Track per-pane health and emit the best aggregate status."""
        self._pane_health[terminal] = status
        statuses = set(self._pane_health.values())
        if "connected" in statuses:
            best = "connected"
        elif "error" in statuses:
            best = "error"
        else:
            best = "disconnected"
        self.health_changed.emit(conn_id, best)

    def _on_pane_disconnected(self, terminal) -> None:
        """Remove a cleanly-closed pane; emit all_closed when the last one goes."""
        if terminal in self._terminals:
            self._terminals.remove(terminal)
        self._pane_health.pop(terminal, None)
        terminal.shutdown()
        terminal.deleteLater()
        if not self._terminals:
            self.all_closed.emit()
