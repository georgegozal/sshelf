# Architecture

## Overview

RemminaMac follows a layered architecture with a clear separation between storage, protocol handling, and UI.

```
┌──────────────────────────────────────────────────────┐
│                        UI layer                      │
│  MainWindow  ConnectionTree  TerminalWidget  Dialogs │
└────────────────────┬─────────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────────┐
│                   Protocol layer                     │
│              SSHWorker  (QThread + paramiko)         │
└────────────────────┬─────────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────────┐
│                   Storage layer                      │
│         Database (SQLite)   Keychain (macOS)         │
└──────────────────────────────────────────────────────┘
```

---

## Layer descriptions

### Storage layer

| Module | Responsibility |
|--------|---------------|
| `src/storage/database.py` | SQLite CRUD for connections and app preferences |
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
| `finished` | — | Session closed cleanly |

Slots it exposes (called from the UI thread via signal/slot or directly — safe because paramiko's channel `send` is thread-safe):

| Method | Purpose |
|--------|---------|
| `send(data: bytes)` | Write keystrokes to the channel |
| `resize(cols, rows)` | Send SIGWINCH to the remote PTY |
| `disconnect()` | Close the channel and trigger `finished` |

### UI layer

#### MainWindow

The top-level window. It owns:
- `ConnectionTree` (left panel)
- `QTabWidget` (right panel) with a permanent **Home tab** at index 0 and closable **terminal tabs** at index ≥ 1

Tab lifecycle:
```
double-click host
      │
      ▼
_open_terminal(conn)
      │  creates TerminalWidget + starts SSHWorker
      │  adds tab to QTabWidget
      ▼
SSHWorker.finished ──► _on_terminal_disconnected ──► removeTab + deleteLater
      or
user clicks ✕ on tab ──► _on_tab_close_requested ──► shutdown + removeTab
```

#### TerminalWidget

A `QWidget` that combines the SSH session lifecycle (`SSHWorker` in `QThread`) with the terminal display (`_PyteTerminal`).

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

#### ConnectionTree

A `QTreeWidget` with two-level hierarchy: group headers → connection items. Emits:
- `connection_selected` on single-click (updates Home tab detail panel)
- `connection_activated` on double-click / Enter (opens terminal tab)
- `selection_cleared` when nothing is selected

---

## Data flow: opening a connection

```
1. User double-clicks a host in ConnectionTree
2. connection_activated(conn) signal → MainWindow._on_connection_activated
3. _open_terminal(conn):
     a. Check if a tab for conn.id already exists → switch to it
     b. Create TerminalWidget(conn)
     c. addTab to QTabWidget
     d. terminal.start_connection()
4. start_connection():
     a. Create QThread + SSHWorker
     b. Move SSHWorker to thread
     c. thread.started → SSHWorker.run()
5. SSHWorker.run() (in background thread):
     a. paramiko.SSHClient.connect(host, port, ...)
     b. open_session() → invoke_shell()
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
