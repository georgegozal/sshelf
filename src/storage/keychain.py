"""
macOS Keychain integration via the keyring library.

Falls back silently if keyring is not installed — passwords remain in SQLite
(legacy behaviour) until the user re-saves a connection.
"""

from __future__ import annotations

_SERVICE = "sshelf"

try:
    import keyring as _keyring
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False


def available() -> bool:
    return _AVAILABLE


def store(conn_id: int, password: str) -> None:
    """Save password to Keychain under the connection id."""
    if _AVAILABLE and password:
        _keyring.set_password(_SERVICE, str(conn_id), password)


def retrieve(conn_id: int) -> str:
    """Return the stored password, or '' if not found."""
    if _AVAILABLE:
        return _keyring.get_password(_SERVICE, str(conn_id)) or ""
    return ""


def delete(conn_id: int) -> None:
    """Remove the stored password (called when a connection is deleted)."""
    if not _AVAILABLE:
        return
    try:
        _keyring.delete_password(_SERVICE, str(conn_id))
    except Exception:
        pass
