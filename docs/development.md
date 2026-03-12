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
    │   ├── connection.py            Connection dataclass + to_dict / from_dict
    │   └── tunnel.py                Tunnel dataclass (id, conn_id, label, type, ports)
    ├── storage/
    │   ├── database.py              SQLite: connections, preferences, snippets, tunnels
    │   └── keychain.py              macOS Keychain wrapper
    ├── protocols/
    │   ├── base.py                  Abstract base for protocol workers
    │   ├── ssh.py                   SSHWorker: paramiko in a QThread
    │   └── tunnel_worker.py         LocalTunnelWorker + RemoteTunnelWorker
    ├── plugins/                     Optional protocol plugins (disabled by default)
    │   ├── rdp/
    │   │   ├── __init__.py          exports RDPWidget
    │   │   ├── widget.py            RDPWidget — status panel, reconnect bar
    │   │   └── worker.py            RDPWorker — launches xfreerdp / mstsc subprocess
    │   └── vnc/
    │       ├── __init__.py          exports VNCWidget
    │       ├── widget.py            VNCWidget + _VNCCanvas — live framebuffer display
    │       └── worker.py            VNCWorker — pure-Python RFB 3.8 client
    └── ui/
        ├── main_window.py           Main window + tab manager + tray + broadcast
        ├── connection_tree.py       Left panel: grouped connection list + health dots
        ├── connection_dialog.py     Add / edit connection dialog (protocol list is dynamic)
        ├── terminal_widget.py       Embedded VT100 terminal (pyte + QPlainTextEdit)
        ├── split_view.py            Horizontal split container for multiple terminal panes
        ├── command_palette.py       Cmd+P fuzzy-search command palette
        ├── welcome_widget.py        Home tab: welcome screen + connection detail
        ├── preferences_dialog.py    App preferences (theme, icon theme, terminal theme, feature toggles)
        ├── ssh_config_import_dialog.py  ~/.ssh/config import UI
        ├── snippets_panel.py        Command snippets side panel (⚡) + JSON export/import
        ├── sftp_panel.py            SFTP file browser side panel
        ├── tunnel_panel.py          Port-forwarding side panel
        ├── themes.py                Built-in terminal color themes (Theme dataclass)
        └── key_gen_dialog.py        SSH key pair generation dialog
```

## Adding a new connection field

1. **Model** — add the field to `Connection` in `src/models/connection.py`. Update `to_dict()` and `from_dict()`.
2. **Schema** — add the column to `_SCHEMA` in `src/storage/database.py`. Add it to both the `INSERT` and `UPDATE` statements in `save_connection()`.
3. **UI** — add an input widget in `src/ui/connection_dialog.py`. Map it in `_load_connection()` and `_build_connection()`.
4. **Protocol** — if it affects the SSH connection, consume it in `SSHWorker.run()` in `src/protocols/ssh.py`.

## Adding a new protocol

Protocols that are always active belong in `src/protocols/`.  Optional protocols go in `src/plugins/<name>/` and are enabled via Preferences → Optional Protocols.

**For a built-in protocol:**
1. Create `src/protocols/<name>.py` with a worker class that subclasses `src/protocols/base.py`.
2. The worker must emit the same signals as `SSHWorker`: `connected`, `data_received(bytes)`, `error(str)`, `finished`.
3. In `MainWindow`, import and wire up the new tab widget.

**For an optional plugin:**
1. Create `src/plugins/<name>/worker.py` (the QThread worker) and `src/plugins/<name>/widget.py` (the tab widget).
2. Create `src/plugins/<name>/__init__.py` that exports the widget class.
3. Add a preference key `enable_<name>` defaulting to `"0"` in `database.py`.
4. In `preferences_dialog.py`, add a checkbox under "Optional Protocols" that reads/writes the preference.
5. In `connection_dialog.py`, append the protocol name to `_protocols` only when the preference is `"1"`.
6. In `main_window.py`, lazy-import the plugin widget inside the `_open_terminal()` branch:
   ```python
   from src.plugins.<name> import <Name>Widget
   ```
7. The plugin widget must expose the same interface as `SplitView`:
   - Signals: `all_closed`, `health_changed(int, str)`, `status_message(str)`
   - Method: `shutdown()`  `matches_conn(conn) → bool`

## Feature toggles

Individual UI features can be enabled or disabled via **Preferences → Terminal Features**.  The preference keys and their defaults are:

| Key | Default | Controls |
|-----|---------|---------|
| `enable_rdp` | `"0"` | RDP protocol option in connection dialog |
| `enable_vnc` | `"0"` | VNC protocol option in connection dialog |
| `feature_broadcast` | `"1"` | Broadcast input (📡) button in toolbar |
| `feature_logging` | `"1"` | Session logging (⏺) button in terminal header |
| `feature_snippets` | `"1"` | ⚡ Commands side panel tab |
| `feature_sftp` | `"1"` | 📁 SFTP file browser side panel tab |
| `feature_tunnels` | `"1"` | 🔀 Port forwarding side panel tab |

All values are stored in the `preferences` table as `"0"` / `"1"` strings.  Read them with `db.get_pref(key, default)`.

Side panel tabs are added conditionally at widget creation time in `TerminalWidget._build_ui()` using a `_tab_idx` counter — never use hardcoded indices when accessing side panel tabs.

---

## CLI flags

```
python main.py [-n SUFFIX] [-u]
```

| Flag | Description |
|------|-------------|
| `-n SUFFIX` / `--name SUFFIX` | Append a custom suffix to the window title |
| `-u` / `--upgrade` | Run `git pull` + `pip install -r requirements.txt` then launch |

---

## Coding conventions

- Python 3.10+, `from __future__ import annotations` in every file.
- PyQt6 signals/slots for all cross-thread communication. Never call UI methods from a background thread directly.
- Lazy imports inside methods (`from src.ui.foo import Foo`) for widgets that are not always needed — avoids circular imports and speeds up startup.
- No global mutable state. Pass `Database` explicitly to every widget that needs it.
- All network / blocking I/O in `QThread` workers. The main thread must stay responsive at all times.
- Always call `thread.quit()` + `thread.wait()` before allowing the owning widget to be deleted. Never rely on `deleteLater()` alone.

## Common tasks

### Inspect the SQLite database

```bash
sqlite3 ~/Library/Application\ Support/RemminaMac/connections.db
.tables
SELECT id, name, host, username FROM connections;
SELECT key, value FROM preferences;
```

### Wipe all data (fresh start)

```bash
rm ~/Library/Application\ Support/RemminaMac/connections.db
```

Keychain entries are not removed by this. Delete them in **Keychain Access.app** → search `RemminaMac` → delete all entries.

### Changing the terminal colour scheme

Terminal themes are defined in `src/ui/themes.py` as frozen `Theme` dataclasses. To add a new theme:

1. Add a `Theme(...)` instance to `_THEMES` in `themes.py`.
2. It will automatically appear in the Preferences → Terminal Theme dropdown.

The active theme is applied at startup by `apply_terminal_theme()` in `terminal_widget.py`. To switch themes at runtime, call `apply_terminal_theme(theme)` and then `refresh_theme()` on each open `_PyteTerminal`.

For quick one-off tweaks, the raw colour globals are at the top of `terminal_widget.py`:

```python
_DEFAULT_FG = "#d4d4d4"   # default foreground
_DEFAULT_BG = "#1e1e1e"   # background
_CURSOR_BG  = "#528bff"   # cursor highlight
_NAMED = { ... }           # ANSI named colours → hex
```

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

Users can also zoom per-connection with `Cmd+=` / `Cmd+-`; that size is persisted automatically.

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
- `thread.wait()` is called after `thread.quit()` before the owning `QObject` can be deleted.
