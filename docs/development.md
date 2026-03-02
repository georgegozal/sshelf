# Development guide

## Setup

```bash
git clone <repo>
cd remminamac

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running

```bash
source .venv/bin/activate
python main.py
```

## Project layout

```
remminamac/
├── main.py                          Entry point — creates QApplication, Database, MainWindow
├── requirements.txt
├── docs/                            This documentation
│   ├── architecture.md
│   ├── terminal-internals.md
│   ├── security.md
│   └── development.md
└── src/
    ├── app.py                       QApplication subclass — theme management
    ├── models/
    │   └── connection.py            Connection dataclass + to_dict / from_dict
    ├── storage/
    │   ├── database.py              SQLite persistence (connections + preferences)
    │   └── keychain.py              macOS Keychain wrapper
    ├── protocols/
    │   ├── base.py                  Abstract base for protocol workers
    │   └── ssh.py                   SSHWorker: paramiko in a QThread
    └── ui/
        ├── main_window.py           Main window + tab manager
        ├── connection_tree.py       Left panel: grouped connection list
        ├── connection_dialog.py     Add / edit connection dialog
        ├── terminal_widget.py       Embedded VT100 terminal (pyte + QPlainTextEdit)
        ├── ssh_config_import_dialog.py  ~/.ssh/config import UI
        ├── welcome_widget.py        Home tab: welcome screen + connection detail
        └── preferences_dialog.py   App preferences
```

## Adding a new connection field

1. **Model** — add the field to `Connection` in `src/models/connection.py`. Update `to_dict()` and `from_dict()`.
2. **Schema** — add the column to `_SCHEMA` in `src/storage/database.py`. Add it to both the `INSERT` and `UPDATE` statements in `save_connection()`.
3. **UI** — add an input widget in `src/ui/connection_dialog.py`. Map it in `_load_connection()` and `_build_connection()`.
4. **Protocol** — if it affects the SSH connection, consume it in `SSHWorker.run()` in `src/protocols/ssh.py`.

## Adding a new protocol

1. Create `src/protocols/<name>.py` with a worker class that subclasses `src/protocols/base.py`.
2. The worker must emit the same signals as `SSHWorker`: `connected`, `data_received(bytes)`, `error(str)`, `finished`.
3. Add a `protocol` field to the `Connection` model.
4. In `TerminalWidget.start_connection()`, select the worker class based on `conn.protocol`.

## Coding conventions

- Python 3.10+, `from __future__ import annotations` in every file.
- PyQt6 signals/slots for all cross-thread communication. Never call UI methods from a background thread directly.
- Lazy imports inside methods (`from src.ui.foo import Foo`) for widgets that are not always needed — avoids circular imports and speeds up startup.
- No global mutable state. Pass `Database` explicitly to every widget that needs it.
- All network / blocking I/O in `QThread` workers. The main thread must stay responsive at all times.

## Common tasks

### Inspect the SQLite database

```bash
sqlite3 ~/Library/Application\ Support/RemminaMac/connections.db
.tables
SELECT id, name, host, username FROM connections;
```

### Wipe all data (fresh start)

```bash
rm ~/Library/Application\ Support/RemminaMac/connections.db
```

Keychain entries are not removed by this. To also clear them:

```bash
python3 -c "
import keyring
# list entries manually in Keychain Access.app → service 'RemminaMac'
"
```

Or delete them in **Keychain Access.app** → search `RemminaMac` → delete all entries.

### Changing the terminal colour scheme

All colour constants are at the top of `src/ui/terminal_widget.py`:

```python
_DEFAULT_FG = "#d4d4d4"   # default foreground
_DEFAULT_BG = "#1e1e1e"   # background
_CURSOR_BG  = "#528bff"   # cursor highlight

_NAMED = { ... }           # ANSI named colours → hex
```

Replace the `_NAMED` palette and the three defaults with your preferred theme.

### Adjusting scrollback size

Change `_HISTORY` in `src/ui/terminal_widget.py`:

```python
_HISTORY = 2000   # lines kept in pyte.HistoryScreen
```

Higher values use more memory but give a longer scrollback buffer.

### Adjusting default font

Change `_FONT_SIZE_DEFAULT` and the font name in `_PyteTerminal.__init__`:

```python
_FONT_SIZE_DEFAULT = 13

font = QFont("Menlo", 13)   # change "Menlo" to any monospace font
```

## Debugging

### SSH connection issues

Set paramiko's log level before running:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Or add it to `main.py` temporarily.

### Terminal rendering issues

`_render()` in `terminal_widget.py` is the main rendering function. Add `print()` statements to inspect `self.screen.buffer`, `self.screen.history`, or `self.screen.in_alt_screen` when investigating display problems.

### Thread issues

All `SSHWorker` signals cross the thread boundary. If you see crashes or Qt warnings about accessing objects from the wrong thread, verify that:
- You are not calling `QWidget` methods directly from `SSHWorker`.
- Signals are connected with the default `AutoConnection` (not `DirectConnection`).
