"""SQLite persistence layer for connections and app preferences."""

from __future__ import annotations

import sqlite3
import os
from pathlib import Path
from typing import List, Optional

from src.models.connection import Connection
from src.storage import keychain


# Store DB in ~/Library/Application Support/RemminaMac/
APP_DATA_DIR = Path.home() / "Library" / "Application Support" / "RemminaMac"
DB_PATH = APP_DATA_DIR / "connections.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS connections (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT    NOT NULL DEFAULT '',
    group_name          TEXT    NOT NULL DEFAULT 'Default',
    host                TEXT    NOT NULL DEFAULT '',
    port                INTEGER NOT NULL DEFAULT 22,
    username            TEXT    NOT NULL DEFAULT '',
    password            TEXT    NOT NULL DEFAULT '',
    private_key_file    TEXT    NOT NULL DEFAULT '',
    passphrase          TEXT    NOT NULL DEFAULT '',
    jump_host           TEXT    NOT NULL DEFAULT '',
    startup_command     TEXT    NOT NULL DEFAULT '',
    keep_alive_interval INTEGER NOT NULL DEFAULT 60,
    forward_agent       INTEGER NOT NULL DEFAULT 0,
    x11_forward         INTEGER NOT NULL DEFAULT 0,
    compression         INTEGER NOT NULL DEFAULT 0,
    notes               TEXT    NOT NULL DEFAULT '',
    tags                TEXT    NOT NULL DEFAULT '',
    color               TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS preferences (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);
"""


class Database:
    """Thin wrapper around a SQLite database for RemminaMac data."""

    def __init__(self, path: Path = DB_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Connection CRUD
    # ------------------------------------------------------------------

    def all_connections(self) -> List[Connection]:
        rows = self._conn.execute(
            "SELECT * FROM connections ORDER BY group_name, name"
        ).fetchall()
        conns = [Connection.from_dict(dict(r)) for r in rows]
        for c in conns:
            self._fill_password(c)
        return conns

    def get_connection(self, conn_id: int) -> Optional[Connection]:
        row = self._conn.execute(
            "SELECT * FROM connections WHERE id = ?", (conn_id,)
        ).fetchone()
        if not row:
            return None
        c = Connection.from_dict(dict(row))
        self._fill_password(c)
        return c

    def _fill_password(self, conn: Connection) -> None:
        """If the DB password is empty, try to load it from Keychain."""
        if not conn.password and conn.id is not None:
            conn.password = keychain.retrieve(conn.id)

    def save_connection(self, conn: Connection) -> Connection:
        """Insert or update a connection. Returns the connection with its id set.

        Passwords are stored in the macOS Keychain when available; the DB
        column is kept empty so credentials never sit in plaintext on disk.
        """
        password = conn.password  # keep in memory; don't write to DB

        d = conn.to_dict()
        d["password"] = ""  # always blank in SQLite

        if conn.id is None:
            cur = self._conn.execute(
                """INSERT INTO connections
                   (name, group_name, host, port, username, password,
                    private_key_file, passphrase, jump_host, startup_command,
                    keep_alive_interval, forward_agent, x11_forward,
                    compression, notes, tags, color)
                   VALUES
                   (:name, :group_name, :host, :port, :username, :password,
                    :private_key_file, :passphrase, :jump_host, :startup_command,
                    :keep_alive_interval, :forward_agent, :x11_forward,
                    :compression, :notes, :tags, :color)""",
                d,
            )
            conn.id = cur.lastrowid
        else:
            self._conn.execute(
                """UPDATE connections SET
                   name=:name, group_name=:group_name, host=:host, port=:port,
                   username=:username, password=:password,
                   private_key_file=:private_key_file, passphrase=:passphrase,
                   jump_host=:jump_host, startup_command=:startup_command,
                   keep_alive_interval=:keep_alive_interval,
                   forward_agent=:forward_agent, x11_forward=:x11_forward,
                   compression=:compression, notes=:notes, tags=:tags, color=:color
                   WHERE id=:id""",
                d,
            )
        self._conn.commit()

        # Persist the password in Keychain (after we have a valid id)
        if password and conn.id is not None:
            keychain.store(conn.id, password)
            conn.password = password  # restore on the in-memory object

        return conn

    def delete_connection(self, conn_id: int) -> None:
        self._conn.execute("DELETE FROM connections WHERE id = ?", (conn_id,))
        self._conn.commit()
        keychain.delete(conn_id)

    def groups(self) -> List[str]:
        """Return distinct group names, sorted."""
        rows = self._conn.execute(
            "SELECT DISTINCT group_name FROM connections ORDER BY group_name"
        ).fetchall()
        return [r[0] for r in rows] or ["Default"]

    # ------------------------------------------------------------------
    # Preferences
    # ------------------------------------------------------------------

    def get_pref(self, key: str, default: str = "") -> str:
        row = self._conn.execute(
            "SELECT value FROM preferences WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else default

    def set_pref(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO preferences (key, value) VALUES (?, ?)"
            "  ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
