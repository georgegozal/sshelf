"""Connection data model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Connection:
    """Represents a single saved connection (SSH, RDP, or VNC)."""

    id: Optional[int] = None
    name: str = ""
    group: str = "Default"

    # Protocol: "ssh" | "rdp" | "vnc"
    protocol: str = "ssh"

    # Network
    host: str = ""
    port: int = 0                 # 0 = use protocol default (22/3389/5900)
    username: str = ""

    # Auth (password is reused for VNC password)
    password: str = ""
    private_key_file: str = ""    # SSH only
    passphrase: str = ""          # SSH only

    # SSH options
    jump_host: str = ""           # ProxyJump  (user@host:port)
    startup_command: str = ""     # Command run right after login
    keep_alive_interval: int = 60 # ServerAliveInterval in seconds
    forward_agent: bool = False
    x11_forward: bool = False
    compression: bool = False

    # RDP options
    rdp_domain: str = ""
    rdp_width: int = 1920
    rdp_height: int = 1080
    rdp_color_depth: int = 32     # 8 | 16 | 24 | 32

    # VNC options
    vnc_view_only: bool = False

    # UI / metadata
    notes: str = ""
    tags: str = ""                # comma-separated tags
    color: str = ""               # hex colour for dot indicator, e.g. "#4caf50"

    # ---------------------------------------------------------------
    # Computed helpers
    # ---------------------------------------------------------------

    def display_name(self) -> str:
        """Human-readable label shown in the tree."""
        return self.name if self.name else self.host

    def default_port(self) -> int:
        """Protocol-specific default port."""
        return {"rdp": 3389, "vnc": 5900}.get(self.protocol, 22)

    def effective_port(self) -> int:
        """Actual port to use: explicit value or protocol default."""
        return self.port if self.port else self.default_port()

    def connection_string(self) -> str:
        """Short connection string (e.g. user@host:port)."""
        user = f"{self.username}@" if self.username else ""
        p    = self.effective_port()
        port = f":{p}" if p != self.default_port() else ""
        if self.protocol == "rdp":
            return f"rdp://{user}{self.host}{port}"
        if self.protocol == "vnc":
            return f"vnc://{self.host}{port}"
        # SSH
        return f"{user}{self.host}{port}"

    def auth_method(self) -> str:
        """Returns the primary auth method label (SSH only)."""
        if self.protocol != "ssh":
            return "Password" if self.password else "—"
        if self.private_key_file:
            return "Key"
        if self.password:
            return "Password"
        return "Agent / Interactive"

    def to_dict(self) -> dict:
        """Serialise to plain dict for DB storage."""
        return {
            "id": self.id,
            "name": self.name,
            "group_name": self.group,
            "protocol": self.protocol,
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "password": self.password,
            "private_key_file": self.private_key_file,
            "passphrase": self.passphrase,
            "jump_host": self.jump_host,
            "startup_command": self.startup_command,
            "keep_alive_interval": self.keep_alive_interval,
            "forward_agent": int(self.forward_agent),
            "x11_forward": int(self.x11_forward),
            "compression": int(self.compression),
            "rdp_domain": self.rdp_domain,
            "rdp_width": self.rdp_width,
            "rdp_height": self.rdp_height,
            "rdp_color_depth": self.rdp_color_depth,
            "vnc_view_only": int(self.vnc_view_only),
            "notes": self.notes,
            "tags": self.tags,
            "color": self.color,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Connection":
        """Deserialise from a DB row dict."""
        return cls(
            id=d.get("id"),
            name=d.get("name", ""),
            group=d.get("group_name", "Default"),
            protocol=d.get("protocol", "ssh"),
            host=d.get("host", ""),
            port=int(d.get("port", 0)),
            username=d.get("username", ""),
            password=d.get("password", ""),
            private_key_file=d.get("private_key_file", ""),
            passphrase=d.get("passphrase", ""),
            jump_host=d.get("jump_host", ""),
            startup_command=d.get("startup_command", ""),
            keep_alive_interval=int(d.get("keep_alive_interval", 60)),
            forward_agent=bool(d.get("forward_agent", 0)),
            x11_forward=bool(d.get("x11_forward", 0)),
            compression=bool(d.get("compression", 0)),
            rdp_domain=d.get("rdp_domain", ""),
            rdp_width=int(d.get("rdp_width", 1920)),
            rdp_height=int(d.get("rdp_height", 1080)),
            rdp_color_depth=int(d.get("rdp_color_depth", 32)),
            vnc_view_only=bool(d.get("vnc_view_only", 0)),
            notes=d.get("notes", ""),
            tags=d.get("tags", ""),
            color=d.get("color", ""),
        )
