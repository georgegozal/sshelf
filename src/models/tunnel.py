"""Tunnel data model for port forwarding."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Tunnel:
    """A single port-forwarding rule associated with a connection."""

    id: Optional[int] = None
    conn_id: Optional[int] = None
    label: str = ""
    type: str = "local"          # "local" | "remote"
    local_port: int = 0
    remote_host: str = "localhost"
    remote_port: int = 0
    enabled: bool = True

    def display(self) -> str:
        if self.type == "local":
            return (
                f"[L] localhost:{self.local_port}"
                f" → {self.remote_host}:{self.remote_port}"
            )
        return (
            f"[R] remote:{self.remote_port}"
            f" → {self.remote_host}:{self.local_port}"
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "conn_id": self.conn_id,
            "label": self.label,
            "type": self.type,
            "local_port": self.local_port,
            "remote_host": self.remote_host,
            "remote_port": self.remote_port,
            "enabled": int(self.enabled),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Tunnel":
        return cls(
            id=d.get("id"),
            conn_id=d.get("conn_id"),
            label=d.get("label", ""),
            type=d.get("type", "local"),
            local_port=int(d.get("local_port", 0)),
            remote_host=d.get("remote_host", "localhost"),
            remote_port=int(d.get("remote_port", 0)),
            enabled=bool(d.get("enabled", 1)),
        )
