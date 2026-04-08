"""
models.py — Modèles de données pour le serveur de supervision.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional


@dataclass
class ClientInfo:
    """Représente un client (élève) connecté à une session."""
    login: str
    group_code: str
    session_id: str
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ip_address: str = ""
    active_window: str = ""
    last_thumb_at: Optional[datetime] = None
    # Per-client directives (e.g. capture_now for a specific client)
    capture_now: bool = False

    @property
    def status(self) -> str:
        """Calcule le statut du client basé sur last_seen."""
        now = datetime.now(timezone.utc)
        delta = (now - self.last_seen).total_seconds()
        if delta < 90:
            return "active"
        elif delta < 300:  # 5 minutes
            return "inactive"
        else:
            return "disconnected"

    def to_dict(self) -> dict:
        return {
            "login": self.login,
            "group_code": self.group_code,
            "session_id": self.session_id,
            "status": self.status,
            "last_seen": self.last_seen.isoformat(),
            "ip_address": self.ip_address,
            "active_window": self.active_window,
            "last_thumb_at": self.last_thumb_at.isoformat() if self.last_thumb_at else None,
        }


@dataclass
class Session:
    """Représente une session de supervision créée par un professeur."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    group_code: str = ""
    teacher_id: str = ""
    label: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc) + timedelta(hours=8))
    auth_token: str = ""
    is_active: bool = True
    directives: dict = field(default_factory=lambda: {
        "block_internet": False,
        "whitelist": [],
        "message": None,
        "open_url": None,
        "capture_now": False,
    })
    clients: dict = field(default_factory=dict)  # login -> ClientInfo

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def active_client_count(self) -> int:
        return sum(1 for c in self.clients.values() if c.status == "active")

    @property
    def inactive_client_count(self) -> int:
        return sum(1 for c in self.clients.values() if c.status == "inactive")

    @property
    def disconnected_client_count(self) -> int:
        return sum(1 for c in self.clients.values() if c.status == "disconnected")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "group_code": self.group_code,
            "teacher_id": self.teacher_id,
            "label": self.label,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "is_active": self.is_active,
            "client_count": len(self.clients),
            "active_count": self.active_client_count,
            "inactive_count": self.inactive_client_count,
            "disconnected_count": self.disconnected_client_count,
        }
