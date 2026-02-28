"""
Embedded SSH terminal widget backed by a pyte VT100 screen buffer.

Architecture
------------
  Raw bytes (SSH) ──► pyte.ByteStream ──► _Screen (pyte.HistoryScreen)
                                                 │
                          QTimer (16 ms) ─────────┘ triggers _render()
                                                 │
                      _PyteTerminal (QPlainTextEdit) ◄── draws screen

Alt-screen mode (vim, htop, …)
  - Detected via DECSET/DECRST 1049 → _Screen.in_alt_screen flag.
  - _render() does a clean full-redraw of the 50-line live buffer only;
    no history rows are touched, so vim can never "stack" frames.

Normal mode
  - History rows appended once (never redrawn).
  - Live screen section replaced on every frame.
"""

from __future__ import annotations

import pyte
from PyQt6.QtCore import QEvent, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QKeyEvent, QPalette, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from src.models.connection import Connection
from src.protocols.ssh import SSHWorker

# ── Terminal dimensions ──────────────────────────────────────────────────────
_PTY_COLS_DEFAULT = 220
_PTY_ROWS_DEFAULT = 50
_HISTORY          = 2000   # scrollback lines kept in pyte

# ── Colour defaults (One Dark) ───────────────────────────────────────────────
_DEFAULT_FG = "#d4d4d4"
_DEFAULT_BG = "#1e1e1e"
_CURSOR_BG  = "#528bff"

# Named ANSI colours → One Dark palette
_NAMED: dict[str, str] = {
    "black":         "#282c34", "red":           "#e06c75",
    "green":         "#98c379", "yellow":        "#e5c07b",
    "blue":          "#61afef", "magenta":       "#c678dd",
    "cyan":          "#56b6c2", "white":         "#abb2bf",
    "brightblack":   "#5c6370", "brightred":     "#e06c75",
    "brightgreen":   "#98c379", "brightyellow":  "#e5c07b",
    "brightblue":    "#61afef", "brightmagenta": "#c678dd",
    "brightcyan":    "#56b6c2", "brightwhite":   "#ffffff",
}


# ── Colour helpers ────────────────────────────────────────────────────────────

def _pyte_color(value: object, is_fg: bool) -> str:
    """Convert a pyte colour value (string, int, tuple) to #RRGGBB."""
    if not value or value == "default":
        return _DEFAULT_FG if is_fg else _DEFAULT_BG
    if isinstance(value, int):
        return _xterm256(value)
    if isinstance(value, (tuple, list)) and len(value) == 3:
        return "#{:02x}{:02x}{:02x}".format(int(value[0]), int(value[1]), int(value[2]))
    if isinstance(value, str):
        if len(value) == 6 and all(c in "0123456789abcdefABCDEF" for c in value):
            return f"#{value}"
        return _NAMED.get(value, _DEFAULT_FG if is_fg else _DEFAULT_BG)
    return _DEFAULT_FG if is_fg else _DEFAULT_BG


def _xterm256(n: int) -> str:
    """xterm 256-colour index → #RRGGBB."""
    if n < 16:
        return list(_NAMED.values())[n % 16]
    if n < 232:
        n -= 16
        b = n % 6; n //= 6
        g = n % 6; r = n // 6
        def v(x: int) -> int: return 0 if x == 0 else 55 + x * 40
        return f"#{v(r):02x}{v(g):02x}{v(b):02x}"
    grey = 8 + (n - 232) * 10
    return f"#{grey:02x}{grey:02x}{grey:02x}"


# ── Patched pyte screen ───────────────────────────────────────────────────────

class _Screen(pyte.HistoryScreen):
    """
    Extends HistoryScreen with two fixes:

    1.  select_graphic_rendition(*attrs, private=False)
        pyte's stream dispatcher calls this with private=True for DEC private
        CSI sequences ending in 'm' (e.g. \x1b[?1m).  pyte's own Screen does
        not accept that keyword → TypeError crash.  We accept and ignore it.

    2.  in_alt_screen flag
        We intercept set_mode / reset_mode for private mode 1049
        (the "save cursor + switch to alternate screen" sequence used by vim,
        htop, less, etc.) and expose a plain boolean.  The renderer uses this
        to skip history and do a clean full-redraw instead.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.in_alt_screen: bool = False

    # ── Fix 1: accept private kwarg on SGR ───────────────────────────────────

    def select_graphic_rendition(self, *attrs: int, private: bool = False) -> None:
        if not private:
            super().select_graphic_rendition(*attrs)

    # ── Fix 2: track alternate-screen mode ───────────────────────────────────

    def set_mode(self, *modes: int, private: bool = False) -> None:
        super().set_mode(*modes, private=private)
        if private and 1049 in modes:
            self.in_alt_screen = True

    def reset_mode(self, *modes: int, private: bool = False) -> None:
        super().reset_mode(*modes, private=private)
        if private and 1049 in modes:
            self.in_alt_screen = False


# ── Main widget ───────────────────────────────────────────────────────────────

class TerminalWidget(QWidget):
    """
    Right-panel widget that opens an interactive SSH session and embeds a
    full VT100 terminal emulator (pyte) so programs like vim / htop work.
    """

    status_message = pyqtSignal(str)
    disconnected   = pyqtSignal(str)

    def __init__(self, connection: Connection, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._conn   = connection
        self._thread: QThread | None   = None
        self._worker: SSHWorker | None = None
        self._build_ui()

    # ── UI ───────────────────────────────────────────────────────────────────

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
            "QPushButton{color:#f55;background:transparent;border:none;}"
            "QPushButton:hover{color:#fff;}"
        )
        btn_disc.clicked.connect(self._on_disconnect)
        hbar.addWidget(btn_disc)
        layout.addWidget(header)

        # Terminal area
        self._output = _PyteTerminal(self)
        self._output.key_pressed.connect(self._on_key)
        self._output.resize_pty.connect(self._on_resize_pty)
        layout.addWidget(self._output)

        # Status bar
        self._status = QLabel("Connecting…")
        self._status.setStyleSheet(
            "background:#1e1e1e;color:#888;padding:2px 8px;font-size:11px;"
        )
        layout.addWidget(self._status)

    def _set_status(self, msg: str) -> None:
        self._status.setText(msg)
        self.status_message.emit(msg)

    # ── Connection lifecycle ─────────────────────────────────────────────────

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

    # ── Worker signals ───────────────────────────────────────────────────────

    def _on_connected(self) -> None:
        self._set_status(f"Connected to {self._conn.connection_string()}")
        self._output.setFocus()

    def _on_data(self, raw: bytes) -> None:
        self._output.feed(raw)

    def _on_error(self, msg: str) -> None:
        self._set_status(f"Error: {msg}")
        self._output.feed(f"\r\n\x1b[31m*** {msg} ***\x1b[0m\r\n".encode())
        self.disconnected.emit(f"Error: {msg}")

    def _on_finished(self) -> None:
        self._set_status("Session closed.")
        self._output.feed(b"\r\n[Session closed]\r\n")
        if self._thread:
            self._thread.quit()
        self.disconnected.emit("Session closed.")

    # ── Key / resize forwarding ──────────────────────────────────────────────

    def _on_key(self, data: bytes) -> None:
        if self._worker:
            self._worker.send(data)

    def _on_resize_pty(self, cols: int, rows: int) -> None:
        if self._worker:
            self._worker.resize(cols, rows)

    # ── Cleanup ──────────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        self._on_disconnect()
        if self._thread:
            self._thread.quit()
            self._thread.wait(2000)
        super().closeEvent(event)


# ── pyte-backed QPlainTextEdit ────────────────────────────────────────────────

class _PyteTerminal(QPlainTextEdit):
    """
    QPlainTextEdit driven by a _Screen (pyte.HistoryScreen) state machine.

    Rendering strategy
    ------------------
    Alt-screen mode  (vim, htop, less, …)
        Detected via _Screen.in_alt_screen.  The entire document is cleared
        and the 50-line live buffer is redrawn on every frame.  History rows
        are never written, so TUI redraws can never stack.

    Normal mode  (plain shell output)
        History rows appended once and never touched again.
        The live screen section (last _PTY_ROWS lines) is replaced each frame.

    Resize
        resizeEvent() recalculates PTY dimensions from the font metrics and
        viewport size, resizes the pyte screen in-place, and emits resize_pty
        so TerminalWidget can forward the new size to paramiko.

    Shortcuts
        event() intercepts Qt ShortcutOverride events for Ctrl/Meta combos so
        they reach keyPressEvent() rather than triggering menu actions.
    """

    key_pressed = pyqtSignal(bytes)
    resize_pty  = pyqtSignal(int, int)   # cols, rows

    # Qt key → ANSI/VT sequence
    _KEY_MAP: dict[int, bytes] = {
        Qt.Key.Key_Up:       b"\x1b[A",
        Qt.Key.Key_Down:     b"\x1b[B",
        Qt.Key.Key_Right:    b"\x1b[C",
        Qt.Key.Key_Left:     b"\x1b[D",
        Qt.Key.Key_Home:     b"\x1b[H",
        Qt.Key.Key_End:      b"\x1b[F",
        Qt.Key.Key_PageUp:   b"\x1b[5~",
        Qt.Key.Key_PageDown: b"\x1b[6~",
        Qt.Key.Key_Delete:   b"\x1b[3~",
        Qt.Key.Key_Insert:   b"\x1b[2~",
        Qt.Key.Key_F1:       b"\x1bOP",
        Qt.Key.Key_F2:       b"\x1bOQ",
        Qt.Key.Key_F3:       b"\x1bOR",
        Qt.Key.Key_F4:       b"\x1bOS",
        Qt.Key.Key_F5:       b"\x1b[15~",
        Qt.Key.Key_F6:       b"\x1b[17~",
        Qt.Key.Key_F7:       b"\x1b[18~",
        Qt.Key.Key_F8:       b"\x1b[19~",
        Qt.Key.Key_F9:       b"\x1b[20~",
        Qt.Key.Key_F10:      b"\x1b[21~",
        Qt.Key.Key_F11:      b"\x1b[23~",
        Qt.Key.Key_F12:      b"\x1b[24~",
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # pyte state machine (uses patched _Screen subclass)
        self.screen = _Screen(_PTY_COLS_DEFAULT, _PTY_ROWS_DEFAULT, history=_HISTORY)
        self.stream = pyte.ByteStream(self.screen)

        # Render throttle
        self._pending = False
        self._timer   = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._render)

        # How many history rows are already written into the document
        self._rendered_history = 0

        # Widget appearance
        self.setReadOnly(True)
        self.setUndoRedoEnabled(False)
        font = QFont("Menlo", 13)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Base, QColor(_DEFAULT_BG))
        pal.setColor(QPalette.ColorRole.Text, QColor(_DEFAULT_FG))
        self.setPalette(pal)
        self.setStyleSheet("border: none; padding: 4px;")
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

    # ── Public API ────────────────────────────────────────────────────────────

    def feed(self, raw: bytes) -> None:
        """Feed raw bytes from the SSH channel; schedule a redraw."""
        self.stream.feed(raw)
        if not self._pending:
            self._pending = True
            self._timer.start()

    # ── PTY resize ────────────────────────────────────────────────────────────

    def _sync_pty_size(self) -> None:
        """Recalculate PTY cols/rows from font metrics and emit resize_pty."""
        fm   = QFontMetrics(self.font())
        char_w = fm.horizontalAdvance(" ")
        char_h = fm.height()
        if char_w == 0 or char_h == 0:
            return

        vp   = self.viewport()
        cols = max(40, vp.width()  // char_w)
        rows = max(10, vp.height() // char_h)

        if cols == self.screen.columns and rows == self.screen.lines:
            return

        self.screen.resize(rows, cols)
        self.resize_pty.emit(cols, rows)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_pty_size()

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _render(self) -> None:
        """
        Choose rendering strategy based on whether pyte is in alt-screen mode.

        Alt-screen (vim / htop / less):
            Clear the whole document and redraw the live 50-line screen.
            History rows are never written, so frames can never stack.

        Normal shell:
            Append any new history rows once, then replace the live screen
            section at the end of the document.
        """
        self._pending = False

        vbar      = self.verticalScrollBar()
        at_bottom = vbar.value() >= vbar.maximum() - 4
        doc       = self.document()

        if self.screen.in_alt_screen:
            # ── Alt-screen: clean full redraw ─────────────────────────────
            self._rendered_history = 0

            cx = self.screen.cursor.x
            cy = self.screen.cursor.y

            cur = QTextCursor(doc)
            cur.select(QTextCursor.SelectionType.Document)
            cur.beginEditBlock()
            cur.removeSelectedText()

            first = True
            for y in range(self.screen.lines):
                if not first:
                    cur.insertBlock()
                first = False
                self._render_row(cur, self.screen.buffer[y], cx if y == cy else -1)

            cur.endEditBlock()
            # In alt screen let pyte control cursor position; don't force scroll.
            return

        # ── Normal mode: incremental history + live screen ────────────────

        # 1. Append new history rows (written once, never redrawn)
        history_rows = list(self.screen.history.top)
        new_count    = len(history_rows)

        if new_count > self._rendered_history:
            new_rows = history_rows[self._rendered_history:]

            hist_block = doc.findBlockByNumber(self._rendered_history)
            if hist_block.isValid():
                ins = QTextCursor(hist_block)
                ins.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            else:
                ins = QTextCursor(doc)
                ins.movePosition(QTextCursor.MoveOperation.End)

            ins.beginEditBlock()
            for row in new_rows:
                self._render_row(ins, row, -1)
                ins.insertBlock()
            ins.endEditBlock()

            self._rendered_history = new_count

        # 2. Replace the live screen section
        cx = self.screen.cursor.x
        cy = self.screen.cursor.y

        screen_block = doc.findBlockByNumber(self._rendered_history)
        cur = QTextCursor(doc)
        cur.beginEditBlock()

        if screen_block.isValid():
            cur.setPosition(screen_block.position())
        else:
            cur.movePosition(QTextCursor.MoveOperation.End)

        cur.movePosition(
            QTextCursor.MoveOperation.End,
            QTextCursor.MoveMode.KeepAnchor,
        )
        cur.removeSelectedText()

        for y in range(self.screen.lines):
            if y > 0 or self._rendered_history > 0 or doc.blockCount() > 1:
                cur.insertBlock()
            self._render_row(cur, self.screen.buffer[y], cx if y == cy else -1)

        cur.endEditBlock()

        if at_bottom:
            lines_below = self.screen.lines - 1 - cy
            if lines_below > 0:
                line_h = QFontMetrics(self.font()).lineSpacing()
                vbar.setValue(max(0, vbar.maximum() - lines_below * line_h))
            else:
                vbar.setValue(vbar.maximum())

    def _render_row(
        self,
        cursor: QTextCursor,
        row: object,
        cursor_x: int,
    ) -> None:
        """
        Write one terminal row into the document, merging adjacent cells
        with identical formatting into a single QTextCharFormat run.
        """
        x    = 0
        cols = self.screen.columns

        while x < cols:
            # Cursor cell — highlighted block
            if x == cursor_x:
                cfmt = QTextCharFormat()
                cfmt.setBackground(QColor(_CURSOR_BG))
                cfmt.setForeground(QColor(_DEFAULT_BG))
                cfmt.setFontWeight(700)
                cursor.insertText(row[x].data or " ", cfmt)
                x += 1
                continue

            # Start of a new run
            first     = row[x]
            fg        = _pyte_color(first.fg, True)
            bg        = _pyte_color(first.bg, False)
            bold      = first.bold
            italic    = first.italics
            underline = first.underscore
            if first.reverse:
                fg, bg = bg, fg

            run: list[str] = []

            while x < cols and x != cursor_x:
                c   = row[x]
                cfg = _pyte_color(c.fg, True)
                cbg = _pyte_color(c.bg, False)
                if c.reverse:
                    cfg, cbg = cbg, cfg
                if (cfg, cbg, c.bold, c.italics, c.underscore) != \
                   (fg,  bg,  bold,  italic,    underline):
                    break
                run.append(c.data or " ")
                x += 1

            fmt = QTextCharFormat()
            fmt.setForeground(QColor(fg))
            fmt.setBackground(QColor(bg))
            if bold:      fmt.setFontWeight(700)
            if italic:    fmt.setFontItalic(True)
            if underline: fmt.setFontUnderline(True)
            cursor.insertText("".join(run), fmt)

    # ── Keyboard handling ─────────────────────────────────────────────────────

    def event(self, event: QEvent) -> bool:
        """Intercept ShortcutOverride so Ctrl/Meta combos reach keyPressEvent."""
        if event.type() == QEvent.Type.ShortcutOverride:
            mods = event.modifiers()
            if mods & (Qt.KeyboardModifier.ControlModifier |
                       Qt.KeyboardModifier.MetaModifier):
                event.accept()
                return True
        return super().event(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key  = event.key()
        mods = event.modifiers()
        text = event.text()

        # Ctrl+[A-Z] → control bytes
        if mods & Qt.KeyboardModifier.ControlModifier:
            char = text.lower()
            if char:
                code = ord(char) - ord("a") + 1
                if 1 <= code <= 26:
                    self.key_pressed.emit(bytes([code]))
                    return

        if key in self._KEY_MAP:
            self.key_pressed.emit(self._KEY_MAP[key])
            return

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
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
