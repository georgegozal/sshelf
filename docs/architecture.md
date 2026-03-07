# Architecture

## Overview

RemminaMac follows a layered architecture with a clear separation between storage, protocol handling, and UI.

```
┌──────────────────────────────────────────────────────────────┐
│                          UI layer                            │
│  MainWindow  ConnectionTree  TerminalWidget  CommandPalette  │
│  SplitView   SnippetsPanel   SFTPPanel       TunnelPanel     │
└────────────────────┬─────────────────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────────────────┐
│                     Protocol layer                           │
│         SSHWorker  LocalTunnelWorker  RemoteTunnelWorker     │
│                  (QThread + paramiko)                        │
└────────────────────┬─────────────────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────────────────┐
│                     Storage layer                            │
│            Database (SQLite)   Keychain (macOS)              │
└──────────────────────────────────────────────────────────────┘
```

---

## Layer descriptions

### Storage layer

| Module | Responsibility |
|--------|---------------|
| `src/storage/database.py` | SQLite CRUD for connections, preferences, snippets, and tunnel rules |
| `src/storage/keychain.py` | Thin wrapper around the `keyring` library for macOS Keychain access |

`Database` is created once in `src/app.py` and passed down to every widget that needs it. There is no global state or singleton.

Passwords are **never written to SQLite**. `save_connection()` blanks the password column and writes to Keychain. `all_connections()` / `get_connection()` populate the password from Keychain when the DB column is empty.

### Protocol layer

`SSHWorker` (`src/protocols/ssh.py`) owns the paramiko `SSHClient` and the interactive shell channel. It lives in a `QThread` so network I/O never blocks the Qt event loop.

Signals it emits back to the UI:

| Signal | Payload | Meaning |
|--------|---------|---------|
| `connected` | — | Channel is open and ready |
| `data_received` | `bytes` | Raw bytes from the remote PTY |
| `error` | `str` | Connection or I/O error |
| `finished` | — | Session closed (clean or otherwise) |

Methods it exposes (safe to call from the UI thread — paramiko's channel `send` is thread-safe):

| Method | Purpose |
|--------|---------|
| `send(data: bytes)` | Write keystrokes to the channel |
| `resize(cols, rows)` | Send SIGWINCH to the remote PTY |
| `disconnect()` | Close the channel and stop the read loop |
| `open_sftp()` | Open an SFTP session on the existing connection |
| `get_transport()` | Return the underlying paramiko `Transport` (used by tunnel workers) |

`LocalTunnelWorker` and `RemoteTunnelWorker` (`src/protocols/tunnel_worker.py`) run in separate QThreads and use the paramiko transport from an existing `SSHWorker` to forward ports.

### UI layer

#### MainWindow

The top-level window. It owns:
- `ConnectionTree` (left panel)
- `QTabWidget` (right panel) with a permanent **Home tab** at index 0 and closable **terminal tabs** at index ≥ 1
- `QSystemTrayIcon` menu bar icon with recent connections and quick-connect
- Broadcast input toggle — when active, keystrokes are mirrored to all open terminal panes

Tab lifecycle:
```
double-click host  (or select via Cmd+P palette)
      │
      ▼
_open_terminal(conn)
      │  creates SplitView → TerminalWidget + starts SSHWorker
      │  adds tab to QTabWidget
      ▼
SSHWorker.finished ──► SplitView.all_closed ──► removeTab + deleteLater
      or
user clicks × Disconnect ──► _on_disconnect ──► waits for thread ──► removeTab
      or
user clicks ✕ on tab ──► _on_tab_close_requested ──► shutdown + removeTab
```

#### SplitView

`SplitView` (`src/ui/split_view.py`) is the tab content widget. It holds one or more `TerminalWidget` panes inside a horizontal `QSplitter`. Each pane has a ⊞ button that opens a new SSH session to the same host in a new pane. When all panes close, `all_closed` is emitted and `MainWindow` removes the tab.

#### TerminalWidget

A `QWidget` that combines the SSH session lifecycle (`SSHWorker` in `QThread`) with the terminal display (`_PyteTerminal`). It also hosts a side panel with three tabs: snippets (⚡), SFTP (📁), and port forwarding (🔀).

```
SSHWorker ──data_received──► _PyteTerminal.feed()
                                    │
                              pyte.ByteStream
                                    │
                              _Screen (pyte.HistoryScreen)
                                    │
                         QTimer 16 ms ──► _render()
                                    │
                          QPlainTextEdit (document)
```

Disconnect lifecycle (safe shutdown, no thread-destroy crash):

```
user clicks × Disconnect
      │
      ├─ if thread already done (error state)
      │      → _do_close() immediately (emit disconnected)
      │
      └─ if thread still running
             → worker.disconnect() (closes socket)
             → _on_finished fires in main thread
                   → thread.wait(2000)   ← join before deleteLater
                   → _do_close()
```

#### CommandPalette

A VSCode-style `QDialog` (`src/ui/command_palette.py`) opened with `Cmd+P`. It lists all saved connections plus app-level commands and filters them with fuzzy matching (every word in the query must appear as a substring of the item label). Arrow keys navigate; Enter activates; Escape closes.

#### ConnectionTree

A `QTreeWidget` with two-level hierarchy: group headers → connection items. Emits:
- `connection_selected` on single-click (updates Home tab detail panel)
- `connection_activated` on double-click / Enter (opens terminal tab)
- `selection_cleared` when nothing is selected

Live green/red health dots on each item are updated via `set_health(conn_id, status)`.

---

## Data flow: opening a connection

```
1. User double-clicks a host in ConnectionTree  (or activates via Cmd+P palette)
2. connection_activated(conn) signal → MainWindow._open_terminal(conn)
3. _open_terminal(conn):
     a. Check if a tab for conn.id already exists → switch to it
     b. Create SplitView(conn) → SplitView creates TerminalWidget
     c. addTab to QTabWidget
     d. TerminalWidget.start_connection()
4. start_connection():
     a. Create QThread + SSHWorker
     b. Move SSHWorker to thread
     c. thread.started → SSHWorker.run()
5. SSHWorker.run() (in background thread):
     a. paramiko.SSHClient.connect(host, port, ...)
     b. open_session() → invoke_shell(term="xterm-256color")
     c. emit connected
     d. loop: channel.recv() → emit data_received(bytes)
6. data_received → _PyteTerminal.feed(raw)
7. QTimer fires every 16 ms → _render() updates QPlainTextEdit
```

---

## Key design decisions

**Why `QPlainTextEdit` as terminal display?**
Using an existing Qt widget gives us text selection, scrollback, and clipboard for free. The downside is that we drive it with rich `QTextCharFormat` runs rather than a GPU-accelerated custom painter, which is fine for typical terminal output volumes.

**Why pyte instead of a custom ANSI parser?**
pyte implements a proper VT100/xterm state machine including alt-screen mode (mode 1049), which is required for vim, htop, less, etc. Rolling a correct parser from scratch is a multi-month project.

**Why a permanent Home tab?**
The Home tab shows connection details on single-click without destroying terminal sessions. It avoids the classic "I clicked the wrong host and killed my SSH session" problem.

**Why `keyring` instead of direct Keychain API calls?**
`keyring` provides a cross-platform interface and handles the macOS Keychain authorization dialog automatically. If someone runs RemminaMac on Linux, passwords stay in the Secret Service instead of failing silently.

**Why `SplitView` wraps `TerminalWidget` instead of using it directly?**
This isolates the split-pane logic from the terminal emulator itself. `TerminalWidget` knows nothing about being one of several panes; `SplitView` aggregates health signals and handles the ⊞ button without touching terminal internals.

**Why `thread.wait()` in `_on_finished`?**
`thread.quit()` is asynchronous — it posts a quit message to the thread's event loop but returns immediately. If the `TerminalWidget` is deleted before the OS thread actually stops, Qt aborts with "QThread: Destroyed while thread is still running". Calling `thread.wait(2000)` after `quit()` ensures the join completes before any `deleteLater()` can fire.
