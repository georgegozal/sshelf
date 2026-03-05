"""Port-forwarding workers that run in background threads."""

from __future__ import annotations

import select
import socket
import threading

from PyQt6.QtCore import QObject, pyqtSignal

from src.models.tunnel import Tunnel


def _pipe(src, dst) -> None:
    """Copy data from src to dst until either side closes."""
    try:
        while True:
            data = src.recv(4096)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass


class LocalTunnelWorker(QObject):
    """
    Listens on ``localhost:<local_port>`` and forwards each connection
    to ``<remote_host>:<remote_port>`` through the SSH transport via
    a ``direct-tcpip`` channel.
    """

    error   = pyqtSignal(str)
    stopped = pyqtSignal()

    def __init__(self, transport, tunnel: Tunnel, parent=None) -> None:
        super().__init__(parent)
        self._transport   = transport
        self._tunnel      = tunnel
        self._running     = False
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._server:
            try:
                self._server.close()
            except OSError:
                pass

    # ------------------------------------------------------------------

    def _run(self) -> None:
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.settimeout(1.0)
            srv.bind(("127.0.0.1", self._tunnel.local_port))
            srv.listen(10)
            self._server = srv
        except OSError as exc:
            self.error.emit(f"Cannot bind port {self._tunnel.local_port}: {exc}")
            self.stopped.emit()
            return

        while self._running:
            try:
                client, _addr = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(
                target=self._handle_client, args=(client,), daemon=True
            ).start()

        self.stopped.emit()

    def _handle_client(self, client: socket.socket) -> None:
        try:
            peer = client.getpeername()
            chan = self._transport.open_channel(
                "direct-tcpip",
                (self._tunnel.remote_host, self._tunnel.remote_port),
                peer,
            )
        except Exception:  # noqa: BLE001
            client.close()
            return

        if chan is None:
            client.close()
            return

        t1 = threading.Thread(target=_pipe, args=(client, chan), daemon=True)
        t2 = threading.Thread(target=_pipe, args=(chan, client), daemon=True)
        t1.start(); t2.start()
        t1.join(); t2.join()
        try:
            chan.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            client.close()
        except OSError:
            pass


class RemoteTunnelWorker(QObject):
    """
    Asks the SSH server to listen on ``<remote_port>`` and forwards
    incoming connections back to ``<remote_host>:<local_port>`` on
    the local machine.
    """

    error   = pyqtSignal(str)
    stopped = pyqtSignal()

    def __init__(self, transport, tunnel: Tunnel, parent=None) -> None:
        super().__init__(parent)
        self._transport = transport
        self._tunnel    = tunnel
        self._running   = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        try:
            self._transport.cancel_port_forward("", self._tunnel.remote_port)
        except Exception:  # noqa: BLE001
            pass

    def _run(self) -> None:
        try:
            self._transport.request_port_forward("", self._tunnel.remote_port)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"Remote forward failed: {exc}")
            self.stopped.emit()
            return

        while self._running:
            chan = self._transport.accept(timeout=1.0)
            if chan is None:
                continue
            threading.Thread(
                target=self._handle_channel, args=(chan,), daemon=True
            ).start()

        self.stopped.emit()

    def _handle_channel(self, chan) -> None:
        try:
            sock = socket.create_connection(
                (self._tunnel.remote_host, self._tunnel.local_port)
            )
        except OSError:
            chan.close()
            return
        t1 = threading.Thread(target=_pipe, args=(chan, sock), daemon=True)
        t2 = threading.Thread(target=_pipe, args=(sock, chan), daemon=True)
        t1.start(); t2.start()
        t1.join(); t2.join()
        try:
            sock.close()
        except OSError:
            pass
