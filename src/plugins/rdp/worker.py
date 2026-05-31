"""RDP session worker — launches xfreerdp / mstsc as a subprocess."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

from src.models.connection import Connection


def _find_xfreerdp() -> Optional[str]:
    """Return the path to xfreerdp3 or xfreerdp, whichever is found first."""
    for name in ("xfreerdp3", "xfreerdp"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _mstsc_path() -> Optional[str]:
    """Return the path to mstsc.exe on Windows."""
    sysroot = os.environ.get("SYSTEMROOT", r"C:\Windows")
    candidate = Path(sysroot) / "system32" / "mstsc.exe"
    return str(candidate) if candidate.exists() else None


class RDPWorker(QObject):
    """
    Manages an RDP session by launching an external client in a subprocess.

    Platforms
    ---------
    macOS / Linux : xfreerdp3 or xfreerdp (must be installed separately)
    Windows       : mstsc.exe (built-in); spawns with a temporary .rdp file
    """

    connected    = pyqtSignal()
    error        = pyqtSignal(str)
    disconnected = pyqtSignal(str)

    def __init__(self, connection: Connection) -> None:
        super().__init__()
        self._conn    = connection
        self._proc:   Optional[subprocess.Popen] = None
        self._running = False
        self._tmp_rdp: Optional[str] = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def disconnect(self) -> None:
        self._running = False
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Main entry point — runs inside QThread
    # ------------------------------------------------------------------

    def run(self) -> None:
        try:
            args = self._build_args()
        except RuntimeError as exc:
            self.error.emit(str(exc))
            return

        try:
            self._proc = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError as exc:
            self.error.emit(f"Could not launch RDP client: {exc}")
            return
        except OSError as exc:
            self.error.emit(str(exc))
            return

        self._running = True
        self.connected.emit()

        # Block until the process exits
        ret = self._proc.wait()

        # Clean up temp file if we created one
        if self._tmp_rdp:
            try:
                os.unlink(self._tmp_rdp)
            except OSError:
                pass
            self._tmp_rdp = None

        if self._running:
            msg = f"RDP session ended (exit code {ret})."
            self.disconnected.emit(msg)
        self._running = False

    # ------------------------------------------------------------------
    # Build the command-line arguments
    # ------------------------------------------------------------------

    def _build_args(self) -> list[str]:
        conn = self._conn
        port = conn.port if conn.port else 3389

        if sys.platform == "win32":
            return self._build_mstsc_args(conn, port)

        # macOS / Linux — try xfreerdp
        xfreerdp = _find_xfreerdp()
        if not xfreerdp:
            raise RuntimeError(
                "xfreerdp not found. Install it with:\n"
                "  macOS:  brew install freerdp\n"
                "  Ubuntu: sudo apt install freerdp2-x11\n"
                "  Arch:   sudo pacman -S freerdp"
            )
        return self._build_xfreerdp_args(xfreerdp, conn, port)

    def _build_xfreerdp_args(
        self, xfreerdp: str, conn: Connection, port: int
    ) -> list[str]:
        args = [xfreerdp]
        args += [f"/v:{conn.host}:{port}"]
        if conn.username:
            args += [f"/u:{conn.username}"]
        if conn.rdp_domain:
            args += [f"/d:{conn.rdp_domain}"]
        if conn.password:
            args += [f"/p:{conn.password}"]
        args += [f"/w:{conn.rdp_width}", f"/h:{conn.rdp_height}"]
        args += [f"/bpp:{conn.rdp_color_depth}"]
        args += ["/clipboard", "+auto-reconnect", "/cert:ignore"]
        return args

    def _build_mstsc_args(self, conn: Connection, port: int) -> list[str]:
        mstsc = _mstsc_path()
        if not mstsc:
            raise RuntimeError("mstsc.exe not found.")

        # Write a temporary .rdp file (mstsc can't accept password on CLI)
        rdp_lines = [
            "screen mode id:i:2",
            f"desktopwidth:i:{conn.rdp_width}",
            f"desktopheight:i:{conn.rdp_height}",
            f"session bpp:i:{conn.rdp_color_depth}",
            f"full address:s:{conn.host}:{port}",
            "redirectclipboard:i:1",
        ]
        if conn.username:
            rdp_lines.append(f"username:s:{conn.username}")
        if conn.rdp_domain:
            rdp_lines.append(f"domain:s:{conn.rdp_domain}")

        fd, tmp = tempfile.mkstemp(suffix=".rdp", prefix="sshelf_")
        with os.fdopen(fd, "w") as f:
            f.write("\r\n".join(rdp_lines) + "\r\n")
        self._tmp_rdp = tmp

        return [mstsc, tmp]
