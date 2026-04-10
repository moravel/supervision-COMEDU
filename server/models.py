"""
models.py — Modèles de données pour le serveur de supervision.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional


@dataclass
class ClientInfo:
    """
    Représente un client (un élève) connecté à une session spécifique.
    Contient toutes les métadonnées nécessaires pour suivre son état de connexion
    et gérer les actions qui lui sont destinées.
    """
    login: str  # Identifiant système de l'élève (souvent le nom d'utilisateur Windows)
    group_code: str  # Le code de session (à 4 lettres) saisi par l'élève
    session_id: str  # L'identifiant interne unique de la session
    
    # Horodatage de la dernière preuve de vie (heartbeat) envoyée par le client
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    ip_address: str = ""  # L'adresse IP locale de la machine de l'élève
    active_window: str = ""  # Le titre de la fenêtre actuellement au premier plan
    
    # Horodatage de la dernière miniature (capture d'écran) reçue
    last_thumb_at: Optional[datetime] = None
    
    # Directives spécifiques à ce client (ex: ordre de prendre une capture immédiate)
    capture_now: bool = False

    @property
    def status(self) -> str:
        """
        Calcule de façon dynamique le statut du client en fonction de l'âge
        de son dernier signal 'heartbeat' (preuve de vie).
        """
        now = datetime.now(timezone.utc)
        delta = (now - self.last_seen).total_seconds()
        
        if delta < 90:
            # Si le dernier heartbeat date de moins de 90 secondes, il est en ligne
            return "active"
        elif delta < 300:
            # Si le dernier heartbeat date de plus de 90s mais moins de 5 minutes
            return "inactive"
        else:
            # Au-delà de 5 minutes sans nouvelles, le client est considéré hors ligne
            return "disconnected"

    def to_dict(self) -> dict:
        """Sérialise l'objet en dictionnaire pour les envois JSON (ex: SSE ou API)."""
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
    """
    Représente une session de supervision créée par un professeur.
    Contrôle l'état global, les directives (blocage internet, urls) et référence
    tous les clients (élèves) qui y sont connectés.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))  # Identifiant interne unique
    group_code: str = ""  # Le code secret à 4 lettres distribué aux élèves
    teacher_id: str = ""  # Identifiant du professeur ayant lancé la session
    label: str = ""  # Nom d'affichage de la session (ex: "Classe 3ème B")
    
    # Date de création et d'expiration (par défaut valide 8 heures pour couvrir une journée)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc) + timedelta(hours=8))
    
    auth_token: str = ""  # Jeton de sécurité pour valider la connexion des élèves
    is_active: bool = True  # Permet de désactiver une session manuellement
    
    # Dictionnaire des directives envoyées par le professeur à appliquer côté client
    directives: dict = field(default_factory=lambda: {
        "block_internet": False,  # True pour bloquer la navigation
        "whitelist": [],          # Liste des URLs autorisées malgré le blocage
        "message": None,          # Un message popup à afficher sur les postes
        "open_url": None,         # Une URL à forcer à s'ouvrir sur les postes
        "capture_now": False,     # Ordre global de forcer une capture d'écran immédiate
    })
    
    # Dictionnaire associant le login (nom d'utilisateur Windows) à l'objet ClientInfo
    clients: dict = field(default_factory=dict)  

    @property
    def is_expired(self) -> bool:
        """Détermine si la session est arrivée à sa date d'expiration."""
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def active_client_count(self) -> int:
        """Compte le nombre total d'élèves actuellement en ligne."""
        return sum(1 for c in self.clients.values() if c.status == "active")

    @property
    def inactive_client_count(self) -> int:
        """Compte le nombre d'élèves inactifs."""
        return sum(1 for c in self.clients.values() if c.status == "inactive")

    @property
    def disconnected_client_count(self) -> int:
        """Compte le nombre d'élèves connectés précédemment mais désormais hors ligne."""
        return sum(1 for c in self.clients.values() if c.status == "disconnected")

    def to_dict(self) -> dict:
        """Sérialise l'objet en dictionnaire pour les APIs et le dashboard frontend."""
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
