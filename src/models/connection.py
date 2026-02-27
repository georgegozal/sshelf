"""Connection data model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Connection:
    """Represents a single saved SSH connection."""

    id: Optional[int] = None
    name: str = ""
    group: str = "Default"

    # Network
    host: str = ""
    port: int = 22
    username: str = ""

    # Auth
    password: str = ""
    private_key_file: str = ""
    passphrase: str = ""

    # SSH options
    jump_host: str = ""           # ProxyJump  (user@host:port)
    startup_command: str = ""     # Command run right after login
    keep_alive_interval: int = 60 # ServerAliveInterval in seconds
    forward_agent: bool = False
    x11_forward: bool = False
    compression: bool = False

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

    def connection_string(self) -> str:
        """Short ssh-style connection string."""
        user = f"{self.username}@" if self.username else ""
        port = f":{self.port}" if self.port != 22 else ""
        return f"{user}{self.host}{port}"

    def auth_method(self) -> str:
        """Returns the primary auth method label."""
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
            host=d.get("host", ""),
            port=int(d.get("port", 22)),
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
            notes=d.get("notes", ""),
            tags=d.get("tags", ""),
            color=d.get("color", ""),
        )
