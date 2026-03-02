# RemminaMac

A Remmina-inspired SSH connection manager for macOS, built with Python and PyQt6.

## Features

### Connection management
- Connections organized into groups with drag-and-drop reordering
- Per-connection settings: port, username, password, SSH key + passphrase, jump host, startup command, color tag, notes
- Quick-connect bar for one-shot connections (`user@host:port`)
- Search/filter connections in real time
- Import connections directly from `~/.ssh/config` (File → Import from ~/.ssh/config…)

### Terminal
- Multi-tab terminal — open multiple SSH sessions simultaneously; each connection gets its own tab
- Full VT100/xterm-256color support — vim, htop, less, nano all work correctly
- Alt-screen programs (vim, htop) render cleanly with no frame stacking
- Dynamic PTY resize — terminal columns/rows follow the window size automatically
- Copy: select text then `Cmd+C` or right-click → Copy
- Paste: `Cmd+V` or right-click → Paste
- Font zoom: `Cmd+=` / `Cmd++` increase, `Cmd+-` decrease, `Cmd+0` reset to default
- Tab color matches the connection's assigned color for quick visual identification
- Session end (typing `exit`) closes the tab automatically

### Security
- Passwords stored in the **macOS Keychain** via the `keyring` library — never written to disk in plaintext
- SSH key authentication with optional passphrase
- Jump host (ProxyJump) support

### UI / UX
- Single-click a connection → shows detail panel in the Home tab without disturbing active terminals
- Double-click a connection → opens or switches to its terminal tab
- Light / Dark / System theme switching (Preferences)
- Window geometry persisted across launches

## Requirements

- macOS 11+
- Python 3.10+

Python dependencies (installed via `pip install -r requirements.txt`):

| Package | Version |
|---------|---------|
| PyQt6 | >= 6.4.0 |
| paramiko | >= 3.3.0 |
| pyte | >= 0.8.0 |
| cryptography | >= 41.0.0 |
| keyring | >= 24.0.0 |

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
source .venv/bin/activate
python main.py
```

## Keyboard shortcuts

| Shortcut | Action |
|----------|--------|
| `Cmd+N` | New connection |
| `Cmd+E` | Edit selected connection |
| `Cmd+Backspace` | Delete selected connection |
| `Cmd+Shift+Q` | Focus quick-connect bar |
| `Cmd+Shift+L` | Toggle connection list panel |
| `Cmd+,` | Preferences |
| `Cmd+Q` | Quit |
| `Cmd+C` | Copy terminal selection |
| `Cmd+V` | Paste to terminal |
| `Cmd+=` / `Cmd++` | Increase terminal font size |
| `Cmd+-` | Decrease terminal font size |
| `Cmd+0` | Reset terminal font size |

## Project structure

```
remminamac/
├── main.py                      Entry point
├── requirements.txt
├── src/
│   ├── app.py                   QApplication subclass, theme management
│   ├── models/
│   │   └── connection.py        Connection data model
│   ├── storage/
│   │   ├── database.py          SQLite persistence (connections + preferences)
│   │   └── keychain.py          macOS Keychain wrapper (keyring)
│   ├── protocols/
│   │   ├── base.py              Base protocol handler
│   │   └── ssh.py               SSH handler (paramiko + jump host support)
│   └── ui/
│       ├── main_window.py            Main application window + tab manager
│       ├── connection_tree.py        Left-panel connection tree
│       ├── connection_dialog.py      Add/edit connection dialog
│       ├── terminal_widget.py        Embedded SSH terminal (pyte VT100)
│       ├── ssh_config_import_dialog.py  ~/.ssh/config import dialog
│       ├── welcome_widget.py         Welcome / detail panel
│       └── preferences_dialog.py     App preferences dialog
```

## Data storage

| Data | Location |
|------|----------|
| Connection metadata | `~/Library/Application Support/RemminaMac/connections.db` |
| Passwords | macOS Keychain (service: `RemminaMac`) |
| Preferences | Same SQLite database, `preferences` table |

## Documentation

Detailed documentation lives in the [`docs/`](docs/) folder:

| Document | Contents |
|----------|----------|
| [architecture.md](docs/architecture.md) | Layer overview, data flow, key design decisions |
| [terminal-internals.md](docs/terminal-internals.md) | pyte integration, rendering strategy, keyboard handling |
| [security.md](docs/security.md) | Keychain storage, SSH auth, known limitations |
| [development.md](docs/development.md) | Dev setup, adding fields/protocols, debugging tips |

## License

RemminaMac is free software released under the **GNU General Public License v3.0**.
See [LICENSE](LICENSE) for the full text.
