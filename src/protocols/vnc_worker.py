"""VNC client worker — pure Python RFB protocol implementation."""

from __future__ import annotations

import socket
import struct
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

from src.models.connection import Connection

# ---------------------------------------------------------------------------
# VNC DES authentication (RFC 6143 §7.2.2)
# ---------------------------------------------------------------------------

def _bit_reverse(b: int) -> int:
    return int(f"{b:08b}"[::-1], 2)


def _vnc_des(challenge: bytes, password: str) -> bytes:
    """Encrypt 16-byte challenge with DES using a bit-reversed VNC key."""
    key = password.encode("latin-1")[:8].ljust(8, b"\x00")
    key = bytes(_bit_reverse(b) for b in key)
    try:
        from cryptography.hazmat.primitives.ciphers.algorithms import DES
    except ImportError:  # cryptography ≥ 42 moved DES to decrepit
        from cryptography.hazmat.decrepit.ciphers.algorithms import DES  # type: ignore
    from cryptography.hazmat.primitives.ciphers import Cipher, modes
    cipher = Cipher(DES(key), modes.ECB())
    enc = cipher.encryptor()
    return enc.update(challenge) + enc.finalize()


# ---------------------------------------------------------------------------
# Qt key → X11 keysym table
# ---------------------------------------------------------------------------

_QT_TO_KEYSYM: dict[int, int] = {
    0x01000000: 0xFF1B,  # Escape
    0x01000001: 0xFF09,  # Tab
    0x01000003: 0xFF08,  # Backspace
    0x01000004: 0xFF0D,  # Return
    0x01000005: 0xFF0D,  # Enter (keypad)
    0x01000006: 0xFF63,  # Insert
    0x01000007: 0xFFFF,  # Delete
    0x01000010: 0xFF50,  # Home
    0x01000011: 0xFF57,  # End
    0x01000016: 0xFFFF,  # Delete (alternate)
    0x01000017: 0xFF55,  # Page Up
    0x01000018: 0xFF56,  # Page Down
    0x01000012: 0xFF51,  # Left
    0x01000013: 0xFF52,  # Up
    0x01000014: 0xFF53,  # Right
    0x01000015: 0xFF54,  # Down
    0x01000020: 0xFFE1,  # Shift_L
    0x01000021: 0xFFE3,  # Control_L
    0x01000022: 0xFFEB,  # Meta_L (Cmd on macOS)
    0x01000023: 0xFF7F,  # Num Lock
    0x01000024: 0xFFE5,  # Caps Lock
    0x01000025: 0xFFE9,  # Alt_L
    0x01000026: 0xFF67,  # Menu
    0x01000027: 0xFF14,  # Scroll Lock
    0x01000009: 0xFF61,  # Print
    0x01000030: 0xFFBE,  # F1
    0x01000031: 0xFFBF,  # F2
    0x01000032: 0xFFC0,  # F3
    0x01000033: 0xFFC1,  # F4
    0x01000034: 0xFFC2,  # F5
    0x01000035: 0xFFC3,  # F6
    0x01000036: 0xFFC4,  # F7
    0x01000037: 0xFFC5,  # F8
    0x01000038: 0xFFC6,  # F9
    0x01000039: 0xFFC7,  # F10
    0x0100003A: 0xFFC8,  # F11
    0x0100003B: 0xFFC9,  # F12
}


def qt_key_to_keysym(qt_key: int, text: str) -> int:
    """Convert a Qt key code + text to an X11 keysym."""
    if qt_key in _QT_TO_KEYSYM:
        return _QT_TO_KEYSYM[qt_key]
    if text and len(text) == 1 and 0x20 <= ord(text[0]) <= 0x7E:
        return ord(text[0])
    return qt_key & 0xFFFF


# ---------------------------------------------------------------------------
# RFB protocol constants
# ---------------------------------------------------------------------------

# Client → server message types
_MSG_SET_PIXEL_FORMAT  = 0
_MSG_SET_ENCODINGS     = 2
_MSG_FB_UPDATE_REQUEST = 3
_MSG_KEY_EVENT         = 4
_MSG_POINTER_EVENT     = 5

# Server → client message types
_MSG_FB_UPDATE         = 0
_MSG_SET_COLOUR_MAP    = 1
_MSG_BELL              = 2
_MSG_SERVER_CUT_TEXT   = 3

# Encoding types (signed 32-bit)
_ENC_RAW      = 0
_ENC_COPYRECT = 1

# VeNCrypt (security type 19) and its sub-types
_SEC_VEENCRYPT = 19
_VEC_PLAIN     = 256
_VEC_TLSNONE   = 257
_VEC_TLSVNC    = 258
_VEC_TLSPLAIN  = 259
_VEC_X509NONE  = 260
_VEC_X509VNC   = 261
_VEC_X509PLAIN = 262


# ---------------------------------------------------------------------------
# VNCWorker
# ---------------------------------------------------------------------------

class VNCWorker(QObject):
    """Manages a VNC (RFB 3.8) session. Move to a QThread before calling run()."""

    # width, height of the remote desktop
    connected    = pyqtSignal(int, int)
    # x, y, w, h, raw RGBX bytes for the updated rectangle
    frame_updated = pyqtSignal(int, int, int, int, bytes)
    error        = pyqtSignal(str)
    disconnected = pyqtSignal(str)

    def __init__(self, connection: Connection) -> None:
        super().__init__()
        self._conn    = connection
        self._sock:   Optional[socket.socket] = None
        self._running = False
        self._width   = 0
        self._height  = 0
        # Internal RGBX framebuffer (updated in-thread; emitted to GUI thread)
        self._fb:     Optional[bytearray] = None

    # ------------------------------------------------------------------
    # Public control interface (called from GUI thread via direct connection
    # or from any thread — socket ops are thread-safe enough for small msgs)
    # ------------------------------------------------------------------

    def send_key(self, keysym: int, down: bool) -> None:
        if self._sock and self._running:
            try:
                self._sock.sendall(
                    struct.pack(">BBHI", _MSG_KEY_EVENT, 1 if down else 0, 0, keysym)
                )
            except OSError:
                pass

    def send_pointer(self, x: int, y: int, button_mask: int) -> None:
        if self._sock and self._running:
            try:
                self._sock.sendall(
                    struct.pack(">BBHH", _MSG_POINTER_EVENT, button_mask, x, y)
                )
            except OSError:
                pass

    def disconnect(self) -> None:
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Main entry point — runs inside QThread
    # ------------------------------------------------------------------

    def run(self) -> None:
        try:
            self._do_connect()
        except Exception as exc:
            self.error.emit(str(exc))
            return

        self._running = True
        try:
            self._main_loop()
        except ConnectionError as exc:
            if self._running:
                self.disconnected.emit(str(exc))
        except OSError as exc:
            if self._running:
                self.error.emit(str(exc))
        except Exception as exc:
            if self._running:
                self.error.emit(str(exc))
        finally:
            self._running = False
            if self._sock:
                try:
                    self._sock.close()
                except OSError:
                    pass

    # ------------------------------------------------------------------
    # Handshake
    # ------------------------------------------------------------------

    def _do_connect(self) -> None:
        host = self._conn.host
        port = self._conn.port if self._conn.port else 5900

        self._sock = socket.create_connection((host, port), timeout=15)
        self._sock.settimeout(60)

        # 1. Version negotiation
        server_ver = self._recv_exactly(12)
        if not server_ver.startswith(b"RFB "):
            raise ConnectionError(f"Not an RFB server (got: {server_ver[:12]!r})")
        self._send(b"RFB 003.008\n")

        # 2. Security type selection
        n_types = struct.unpack("B", self._recv_exactly(1))[0]
        if n_types == 0:
            rlen, = struct.unpack(">I", self._recv_exactly(4))
            reason = self._recv_exactly(rlen).decode("utf-8", errors="replace")
            raise ConnectionError(f"Server rejected connection: {reason}")
        types = list(self._recv_exactly(n_types))

        if _SEC_VEENCRYPT in types:          # VeNCrypt TLS wrapper — preferred
            self._send(bytes([_SEC_VEENCRYPT]))
            self._do_veencrypt()             # handles its own SecurityResult
        elif 2 in types and self._conn.password:
            self._send(bytes([2]))           # VNC Authentication
            challenge = self._recv_exactly(16)
            self._send(_vnc_des(challenge, self._conn.password))
            self._check_security_result()
        elif 1 in types:
            self._send(bytes([1]))           # No Authentication
            self._check_security_result()
        else:
            raise ConnectionError(
                "No supported security type available (server requires: "
                + ", ".join(str(t) for t in types) + ")"
            )

        # 3. ClientInit — shared=1 (don't disconnect other clients)
        self._send(bytes([1]))

        # 4. ServerInit
        self._width, self._height = struct.unpack(">HH", self._recv_exactly(4))
        self._recv_exactly(16)      # server pixel format (we override below)
        nlen, = struct.unpack(">I", self._recv_exactly(4))
        self._recv_exactly(nlen)    # server name (ignored)

        # 5. SetPixelFormat: 32bpp, RGBX, little-endian
        #    red-shift=0, green-shift=8, blue-shift=16
        #    → in memory: byte0=R, byte1=G, byte2=B, byte3=X
        #    → matches QImage.Format.Format_RGBX8888
        pf = struct.pack(
            ">BBBBHHHBBBxxx",
            32,   # bits-per-pixel
            24,   # depth
            0,    # big-endian-flag (little-endian)
            1,    # true-colour-flag
            255,  # red-max
            255,  # green-max
            255,  # blue-max
            0,    # red-shift
            8,    # green-shift
            16,   # blue-shift
        )
        self._send(struct.pack(">Bxxx", _MSG_SET_PIXEL_FORMAT) + pf)

        # 6. SetEncodings: Raw, CopyRect
        self._send(struct.pack(">BxH", _MSG_SET_ENCODINGS, 2))
        self._send(struct.pack(">ii", _ENC_RAW, _ENC_COPYRECT))

        # Allocate framebuffer
        self._fb = bytearray(self._width * self._height * 4)
        self.connected.emit(self._width, self._height)

    # ------------------------------------------------------------------
    # Security helpers
    # ------------------------------------------------------------------

    def _check_security_result(self) -> None:
        """Read and verify the RFB 3.8 SecurityResult message."""
        result, = struct.unpack(">I", self._recv_exactly(4))
        if result != 0:
            try:
                rlen, = struct.unpack(">I", self._recv_exactly(4))
                reason = self._recv_exactly(rlen).decode("utf-8", errors="replace")
            except Exception:
                reason = "Authentication failed"
            raise ConnectionError(f"Authentication failed: {reason}")

    def _do_veencrypt(self) -> None:
        """VeNCrypt (security type 19) sub-protocol: version, sub-type, TLS, auth."""
        import ssl

        # Version exchange — server sends major.minor, we echo back
        major, minor = struct.unpack("BB", self._recv_exactly(2))
        if major != 0 or minor < 2:
            raise ConnectionError(f"Unsupported VeNCrypt version: {major}.{minor}")
        self._send(bytes([0, 2]))
        ack = struct.unpack("B", self._recv_exactly(1))[0]
        if ack != 0:
            raise ConnectionError("Server rejected VeNCrypt version 0.2")

        # Sub-type negotiation
        n = struct.unpack("B", self._recv_exactly(1))[0]
        subtypes = list(struct.unpack(f">{n}I", self._recv_exactly(n * 4)))
        chosen = self._choose_veencrypt_subtype(subtypes)
        if chosen is None:
            raise ConnectionError(
                "No supported VeNCrypt sub-type (server offers: "
                + ", ".join(str(s) for s in subtypes) + ")"
            )
        self._send(struct.pack(">I", chosen))
        ack = struct.unpack("B", self._recv_exactly(1))[0]
        if ack != 1:
            raise ConnectionError(f"Server rejected VeNCrypt sub-type {chosen}")

        # Wrap in TLS for all TLS/X509 sub-types (not sub-type 256 Plain)
        if chosen != _VEC_PLAIN:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            self._sock = ctx.wrap_socket(self._sock)

        # Sub-type authentication
        if chosen in (_VEC_TLSVNC, _VEC_X509VNC):
            challenge = self._recv_exactly(16)
            self._send(_vnc_des(challenge, self._conn.password or ""))
        elif chosen in (_VEC_TLSPLAIN, _VEC_X509PLAIN, _VEC_PLAIN):
            uname = (self._conn.username or "").encode("utf-8")
            passwd = (self._conn.password or "").encode("utf-8")
            self._send(struct.pack(">II", len(uname), len(passwd)) + uname + passwd)
        # _VEC_TLSNONE / _VEC_X509NONE: no auth data needed

        # VeNCrypt always sends its own SecurityResult
        self._check_security_result()

    def _choose_veencrypt_subtype(self, subtypes: list) -> "int | None":
        """Select best VeNCrypt sub-type from the server-offered list."""
        if self._conn.password:
            preference = [
                _VEC_TLSVNC, _VEC_X509VNC,
                _VEC_TLSPLAIN, _VEC_X509PLAIN,
                _VEC_PLAIN, _VEC_TLSNONE, _VEC_X509NONE,
            ]
        else:
            preference = [
                _VEC_TLSNONE, _VEC_X509NONE,
                _VEC_TLSVNC, _VEC_X509VNC,
                _VEC_TLSPLAIN, _VEC_X509PLAIN, _VEC_PLAIN,
            ]
        for sub in preference:
            if sub in subtypes:
                return sub
        return None

    # ------------------------------------------------------------------
    # Main receive loop
    # ------------------------------------------------------------------

    def _main_loop(self) -> None:
        self._request_update(incremental=False)

        while self._running:
            msg_type = struct.unpack("B", self._recv_exactly(1))[0]

            if msg_type == _MSG_FB_UPDATE:
                self._handle_framebuffer_update()
                self._request_update(incremental=True)

            elif msg_type == _MSG_SET_COLOUR_MAP:
                # padding(1) + first-colour(2) + num-colours(2)
                first, num = struct.unpack(">xHH", self._recv_exactly(5))
                self._recv_exactly(num * 6)  # 3×U16 per colour entry

            elif msg_type == _MSG_BELL:
                pass

            elif msg_type == _MSG_SERVER_CUT_TEXT:
                self._recv_exactly(3)  # padding
                length, = struct.unpack(">I", self._recv_exactly(4))
                self._recv_exactly(length)

            else:
                raise ConnectionError(f"Unknown server message type: {msg_type}")

    def _handle_framebuffer_update(self) -> None:
        # padding(1) + num-rects(2)
        n_rects, = struct.unpack(">xH", self._recv_exactly(3))

        for _ in range(n_rects):
            x, y, w, h, enc = struct.unpack(">HHHHi", self._recv_exactly(12))

            if enc == _ENC_RAW:
                data = self._recv_exactly(w * h * 4)
                self._blit(x, y, w, h, data)
                self.frame_updated.emit(x, y, w, h, bytes(data))

            elif enc == _ENC_COPYRECT:
                src_x, src_y = struct.unpack(">HH", self._recv_exactly(4))
                data = self._extract_rect(src_x, src_y, w, h)
                self._blit(x, y, w, h, data)
                self.frame_updated.emit(x, y, w, h, data)

            else:
                # Unknown encoding — can't recover, the stream is now misaligned
                raise ConnectionError(f"Unsupported encoding: {enc}")

    # ------------------------------------------------------------------
    # Framebuffer helpers
    # ------------------------------------------------------------------

    def _blit(self, x: int, y: int, w: int, h: int, data: bytes | bytearray) -> None:
        if self._fb is None or w == 0 or h == 0:
            return
        stride = self._width * 4
        row_w  = w * 4
        for row in range(h):
            dst = (y + row) * stride + x * 4
            src = row * row_w
            self._fb[dst: dst + row_w] = data[src: src + row_w]

    def _extract_rect(self, x: int, y: int, w: int, h: int) -> bytes:
        if self._fb is None or w == 0 or h == 0:
            return b"\x00" * (w * h * 4)
        stride = self._width * 4
        row_w  = w * 4
        out = bytearray(h * row_w)
        for row in range(h):
            src = (y + row) * stride + x * 4
            dst = row * row_w
            out[dst: dst + row_w] = self._fb[src: src + row_w]
        return bytes(out)

    def _request_update(self, incremental: bool) -> None:
        if self._sock and self._running:
            try:
                self._sock.sendall(
                    struct.pack(
                        ">BBHHHH",
                        _MSG_FB_UPDATE_REQUEST,
                        1 if incremental else 0,
                        0, 0, self._width, self._height,
                    )
                )
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Socket helpers
    # ------------------------------------------------------------------

    def _send(self, data: bytes) -> None:
        if self._sock:
            self._sock.sendall(data)

    def _recv_exactly(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("Connection closed by server")
            buf += chunk
        return buf
