"""SSH backend using paramiko — runs in a dedicated QThread."""

from __future__ import annotations

import os
import socket
import threading
import time
from pathlib import Path
from typing import Optional

import paramiko
from PyQt6.QtCore import QObject, pyqtSignal, QThread

from src.models.connection import Connection


class SSHWorker(QObject):
    """
    Manages the paramiko SSH session.

    Designed to live in a QThread (see TerminalWidget).

    Signals
    -------
    connected()                  — shell channel is open
    data_received(bytes)         — raw bytes from the remote shell
    error(str)                   — connection / auth error message
    finished()                   — session fully closed
    """

    connected = pyqtSignal()
    data_received = pyqtSignal(bytes)
    error = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, connection: Connection) -> None:
        super().__init__()
        self._conn = connection
        self._client: Optional[paramiko.SSHClient] = None
        self._channel: Optional[paramiko.Channel] = None
        self._running = False

    # ------------------------------------------------------------------
    # Public slot — called from the thread's start event
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Open the SSH session and start reading in a loop."""
        try:
            self._client = self._build_client()
            self._client.connect(**self._connect_kwargs())
            self._channel = self._client.invoke_shell(
                term="xterm-256color",
                width=200,
                height=50,
            )
            self._channel.setblocking(False)
            self._running = True
            self.connected.emit()

            if self._conn.startup_command:
                self.send(self._conn.startup_command + "\n")

            self._read_loop()

        except paramiko.AuthenticationException as exc:
            self.error.emit(f"Authentication failed: {exc}")
        except paramiko.SSHException as exc:
            self.error.emit(f"SSH error: {exc}")
        except socket.gaierror as exc:
            self.error.emit(f"Cannot resolve host '{self._conn.host}': {exc}")
        except OSError as exc:
            self.error.emit(f"Network error: {exc}")
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"Unexpected error: {exc}")
        finally:
            self._cleanup()
            self.finished.emit()

    def send(self, data: str | bytes) -> None:
        """Send raw bytes (or a UTF-8 string) to the remote shell."""
        if not self._channel or not self._running:
            return
        if isinstance(data, str):
            data = data.encode("utf-8", errors="replace")
        try:
            self._channel.sendall(data)
        except OSError:
            pass

    def resize(self, cols: int, rows: int) -> None:
        """Notify remote of terminal size change."""
        if self._channel and self._running:
            try:
                self._channel.resize_pty(width=cols, height=rows)
            except OSError:
                pass

    def open_sftp(self):
        """Open an SFTP session on the existing connection. Thread-safe."""
        if self._client:
            try:
                return self._client.open_sftp()
            except Exception:  # noqa: BLE001
                return None
        return None

    def get_transport(self):
        """Return the underlying paramiko Transport (used by tunnel workers)."""
        if self._client:
            return self._client.get_transport()
        return None

    def disconnect(self) -> None:
        self._running = False
        self._cleanup()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _read_loop(self) -> None:
        while self._running:
            if self._channel.closed or self._channel.eof_received:
                break
            try:
                chunk = self._channel.recv(4096)
                if chunk:
                    self.data_received.emit(chunk)
                else:
                    time.sleep(0.02)
            except socket.timeout:
                time.sleep(0.02)
            except OSError:
                break

    def _cleanup(self) -> None:
        self._running = False
        try:
            if self._channel:
                self._channel.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            if self._client:
                self._client.close()
        except Exception:  # noqa: BLE001
            pass

    def _build_client(self) -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        return client

    def _connect_kwargs(self) -> dict:
        c = self._conn
        kwargs: dict = {
            "hostname": c.host,
            "port": c.port,
            "username": c.username or None,
            "timeout": 15,
            "allow_agent": True,
            "look_for_keys": True,
            "compress": c.compression,
        }

        if c.password:
            kwargs["password"] = c.password
            kwargs["look_for_keys"] = False
            kwargs["allow_agent"] = False

        if c.private_key_file:
            key_path = os.path.expanduser(c.private_key_file)
            try:
                pkey = self._load_key(key_path, c.passphrase or None)
                kwargs["pkey"] = pkey
                kwargs["look_for_keys"] = False
            except Exception as exc:  # noqa: BLE001
                raise paramiko.SSHException(
                    f"Cannot load key '{key_path}': {exc}"
                ) from exc

        if c.jump_host:
            sock = self._open_jump_tunnel(c)
            kwargs["sock"] = sock

        if c.keep_alive_interval > 0:
            # Will be set on the transport after connect — done in run()
            pass

        return kwargs

    @staticmethod
    def _load_key(path: str, passphrase: str | None) -> paramiko.PKey:
        """Try all key types in order."""
        for cls in (
            paramiko.Ed25519Key,
            paramiko.ECDSAKey,
            paramiko.RSAKey,
            paramiko.DSSKey,
        ):
            try:
                return cls.from_private_key_file(path, password=passphrase)
            except paramiko.SSHException:
                continue
        raise paramiko.SSHException(f"Unsupported key format: {path}")

    @staticmethod
    def _open_jump_tunnel(conn: Connection) -> socket.socket:
        """Open a TCP tunnel through a jump host using a second paramiko client."""
        raw = conn.jump_host
        # Format: [user@]host[:port]
        username = None
        if "@" in raw:
            username, raw = raw.split("@", 1)
        if ":" in raw:
            jump_host, jump_port_str = raw.rsplit(":", 1)
            jump_port = int(jump_port_str)
        else:
            jump_host, jump_port = raw, 22

        jump_client = paramiko.SSHClient()
        jump_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        jump_client.connect(
            hostname=jump_host,
            port=jump_port,
            username=username,
            timeout=10,
            allow_agent=True,
            look_for_keys=True,
        )
        transport = jump_client.get_transport()
        dest = (conn.host, conn.port)
        src = ("127.0.0.1", 0)
        channel = transport.open_channel("direct-tcpip", dest, src)
        return channel  # type: ignore[return-value]
