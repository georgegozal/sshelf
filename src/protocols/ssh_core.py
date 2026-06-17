"""Pure-paramiko SSH helpers — no Qt dependency.

These functions are shared by SSHWorker (GUI path) and the CLI session
layer so that connection/auth logic has a single source of truth.
"""

from __future__ import annotations

import os
import socket

import paramiko

from src.models.connection import Connection


def connect_sock(host: str, port: int, timeout: float = 15) -> socket.socket:
    """Resolve host:port and return a connected socket, preferring IPv4.

    Sorting AF_INET first avoids failures with IPv6 link-local addresses
    (fe80::...) that mDNS/.local hostnames often resolve to on macOS.
    """
    infos = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
    infos.sort(key=lambda x: 0 if x[0] == socket.AF_INET else 1)
    last_exc: Exception = OSError(f"Cannot connect to {host}:{port}")
    for af, socktype, proto, _canonname, sockaddr in infos:
        try:
            sock = socket.socket(af, socktype, proto)
            sock.settimeout(timeout)
            sock.connect(sockaddr)
            return sock
        except OSError as exc:
            last_exc = exc
            try:
                sock.close()
            except OSError:
                pass
    raise last_exc


def load_key(path: str, passphrase: str | None) -> paramiko.PKey:
    """Try all key types in order (Ed25519 → ECDSA → RSA → DSS)."""
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


def open_jump_tunnel(conn: Connection) -> socket.socket:
    """Open a TCP tunnel through a jump host using a second paramiko client.

    jump_host format: [user@]host[:port]
    """
    raw = conn.jump_host
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


def build_client() -> paramiko.SSHClient:
    """Create a paramiko SSHClient with auto-accept host key policy."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    return client


def connect_kwargs(conn: Connection) -> dict:
    """Build the kwargs dict for paramiko SSHClient.connect()."""
    port = conn.effective_port()
    kwargs: dict = {
        "hostname": conn.host,
        "port": port,
        "username": conn.username or None,
        "timeout": 15,
        "allow_agent": True,
        "look_for_keys": True,
        "compress": conn.compression,
    }

    if conn.password:
        kwargs["password"] = conn.password
        kwargs["look_for_keys"] = False
        kwargs["allow_agent"] = False

    if conn.private_key_file:
        key_path = os.path.expanduser(conn.private_key_file)
        try:
            pkey = load_key(key_path, conn.passphrase or None)
            kwargs["pkey"] = pkey
            kwargs["look_for_keys"] = False
        except Exception as exc:  # noqa: BLE001
            raise paramiko.SSHException(
                f"Cannot load key '{key_path}': {exc}"
            ) from exc

    if conn.jump_host:
        kwargs["sock"] = open_jump_tunnel(conn)
    else:
        kwargs["sock"] = connect_sock(conn.host, port, timeout=15)

    return kwargs


def establish(conn: Connection) -> paramiko.SSHClient:
    """Build and return a connected paramiko SSHClient for *conn*."""
    client = build_client()
    client.connect(**connect_kwargs(conn))
    return client
