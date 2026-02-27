# RemminaMac

A Remmina-inspired SSH connection manager for macOS, built with Python and PyQt6.

## Features

- Manage SSH connections organized into groups
- Embedded terminal with full interactive shell support
- Per-connection settings: port, username, key file, jump host, startup command
- Quick-connect bar for one-shot connections
- Persistent storage via SQLite
- Search/filter connections
- macOS-native look and feel (dark mode aware)

## Requirements

- macOS 11+
- Python 3.10+
- PyQt6
- paramiko

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python main.py
```

## Project Structure

```
remminamac/
├── main.py                 Entry point
├── src/
│   ├── app.py              QApplication subclass
│   ├── models/
│   │   └── connection.py   Connection data model
│   ├── storage/
│   │   └── database.py     SQLite persistence layer
│   ├── protocols/
│   │   ├── base.py         Base protocol handler
│   │   └── ssh.py          SSH handler (paramiko)
│   └── ui/
│       ├── main_window.py      Main application window
│       ├── connection_tree.py  Left-panel connection tree
│       ├── connection_dialog.py Add/edit connection dialog
│       ├── terminal_widget.py  Embedded SSH terminal
│       ├── welcome_widget.py   Welcome / detail panel
│       └── preferences_dialog.py App preferences
```
