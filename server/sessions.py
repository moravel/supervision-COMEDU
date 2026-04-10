"""
sessions.py — Gestionnaire de sessions de supervision.
Stockage in-memory avec persistance JSON optionnelle.
"""

import json
import os
import random
import string
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from models import Session, ClientInfo

logger = logging.getLogger(__name__)

# Alphabet sans confusion visuelle (exclus: 0, O, 1, I, L)
GROUP_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
GROUP_CODE_LENGTH = 4
SESSIONS_FILE = "data/sessions.json"


class SessionManager:
    """
    Gère le cycle de vie de toutes les sessions de supervision en mémoire serveur.
    C'est le composant central qui gère le CRUD (Création, Lecture, Mise à jour, Suppression)
    des sessions et des élèves (clients) connectés, tout en gérant la persistance sur disque
    via un fichier JSON pour ne rien perdre en cas de redémarrage du serveur.
    """

    def __init__(self):
        self.sessions: dict[str, Session] = {}  # Associe un code de groupe à l'objet Session
        self._load_from_disk()

    # ── Persistance JSON ─────────────────────────────────────────

    def _load_from_disk(self):
        """Charge les sessions depuis le fichier JSON au démarrage."""
        if not os.path.exists(SESSIONS_FILE):
            return
        try:
            with open(SESSIONS_FILE, "r") as f:
                data = json.load(f)
            for item in data:
                session = Session(
                    id=item["id"],
                    group_code=item["group_code"],
                    teacher_id=item["teacher_id"],
                    label=item["label"],
                    created_at=datetime.fromisoformat(item["created_at"]),
                    expires_at=datetime.fromisoformat(item["expires_at"]),
                    auth_token=item.get("auth_token", ""),
                    is_active=item["is_active"],
                    directives=item.get("directives", {}),
                )
                for cl in item.get("clients", []):
                    client = ClientInfo(
                        login=cl["login"],
                        group_code=cl["group_code"],
                        session_id=cl["session_id"],
                        last_seen=datetime.fromisoformat(cl["last_seen"]),
                        ip_address=cl.get("ip_address", ""),
                        active_window=cl.get("active_window", ""),
                        last_thumb_at=datetime.fromisoformat(cl["last_thumb_at"]) if cl.get("last_thumb_at") else None,
                    )
                    session.clients[client.login] = client
                self.sessions[session.group_code] = session
            logger.info(f"Loaded {len(self.sessions)} sessions from disk.")
        except Exception as e:
            logger.error(f"Failed to load sessions from disk: {e}")

    def _save_to_disk(self):
        """Persiste toutes les sessions sur disque."""
        os.makedirs(os.path.dirname(SESSIONS_FILE), exist_ok=True)
        try:
            data = []
            for session in self.sessions.values():
                s = {
                    "id": session.id,
                    "group_code": session.group_code,
                    "teacher_id": session.teacher_id,
                    "label": session.label,
                    "created_at": session.created_at.isoformat(),
                    "expires_at": session.expires_at.isoformat(),
                    "auth_token": session.auth_token,
                    "is_active": session.is_active,
                    "directives": session.directives,
                    "clients": [
                        {
                            "login": c.login,
                            "group_code": c.group_code,
                            "session_id": c.session_id,
                            "last_seen": c.last_seen.isoformat(),
                            "ip_address": c.ip_address,
                            "active_window": c.active_window,
                            "last_thumb_at": c.last_thumb_at.isoformat() if c.last_thumb_at else None,
                        }
                        for c in session.clients.values()
                    ],
                }
                data.append(s)
            with open(SESSIONS_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save sessions to disk: {e}")

    # ── Génération code groupe ───────────────────────────────────

    def _generate_group_code(self) -> str:
        """
        Génère un code de groupe (ex: 'AMK7') aléatoire de 4 caractères pour rejoindre une session.
        L'alphabet utilisé exclut volontairement les caractères ambigus (0, O, 1, l) 
        pour éviter les erreurs de saisie par les élèves.
        """
        active_codes = {
            code for code, s in self.sessions.items() if s.is_active
        }
        for _ in range(1000):  # Protection contre une boucle infinie en cas de saturation
            code = "".join(random.choices(GROUP_CODE_ALPHABET, k=GROUP_CODE_LENGTH))
            if code not in active_codes:
                return code
        raise RuntimeError("Impossible de générer un code de groupe unique après 1000 tentatives")

    # ── CRUD Sessions ────────────────────────────────────────────

    def create_session(self, teacher_id: str, label: str = "", expires_in_hours: float = 8) -> Session:
        """Crée une nouvelle session et retourne l'objet Session."""
        session = Session(
            group_code=self._generate_group_code(),
            teacher_id=teacher_id,
            label=label,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=expires_in_hours),
            auth_token=os.urandom(16).hex(),
        )
        self.sessions[session.group_code] = session
        self._save_to_disk()
        logger.info(f"Session created: {session.group_code} by {teacher_id}")
        return session

    def close_session(self, group_code: str) -> bool:
        """Ferme une session (is_active = False)."""
        session = self.sessions.get(group_code)
        if not session:
            return False
        session.is_active = False
        self._save_to_disk()
        logger.info(f"Session closed: {group_code}")
        return True

    def get_session(self, group_code: str) -> Optional[Session]:
        """Retourne une session par son code groupe."""
        session = self.sessions.get(group_code)
        if session and session.is_active and session.is_expired:
            session.is_active = False
            self._save_to_disk()
            logger.info(f"Session expired: {group_code}")
        return session

    def get_active_session(self, group_code: str) -> Optional[Session]:
        """Retourne une session active par son code groupe."""
        session = self.get_session(group_code)
        if session and session.is_active:
            return session
        return None

    def get_teacher_sessions(self, teacher_id: str) -> list[Session]:
        """Retourne toutes les sessions d'un professeur."""
        # Vérifier les expirations
        for s in self.sessions.values():
            if s.is_active and s.is_expired:
                s.is_active = False
        self._save_to_disk()
        return [s for s in self.sessions.values() if s.teacher_id == teacher_id]

    # ── Gestion Clients ──────────────────────────────────────────

    def register_client(self, group_code: str, login: str, ip_address: str = "") -> tuple[Optional[ClientInfo], Optional[str]]:
        """
        Enregistre ou met à jour un client dans une session.
        Retourne (ClientInfo, None) en cas de succès, (None, error_code) en cas d'erreur.
        error_code: "not_found", "session_closed", "login_already_bound"
        """
        session = self.sessions.get(group_code)
        if not session:
            return None, "not_found"

        if not session.is_active or session.is_expired:
            if session.is_active:
                session.is_active = False
                self._save_to_disk()
            return None, "session_closed"

        # Vérifier liaison unique : ce login est-il déjà lié à un AUTRE group_code actif ?
        for code, s in self.sessions.items():
            if code != group_code and s.is_active and not s.is_expired:
                if login in s.clients:
                    return None, "login_already_bound"

        # Enregistrer ou mettre à jour le client
        if login in session.clients:
            client = session.clients[login]
            client.last_seen = datetime.now(timezone.utc)
            client.ip_address = ip_address
        else:
            client = ClientInfo(
                login=login,
                group_code=group_code,
                session_id=session.id,
                ip_address=ip_address,
            )
            session.clients[login] = client
            logger.info(f"Client registered: {login} in session {group_code}")

        self._save_to_disk()
        return client, None

    def update_client(self, group_code: str, login: str,
                      active_window: str = None,
                      last_thumb_at: datetime = None,
                      ip_address: str = None):
        """Met à jour les informations d'un client."""
        session = self.sessions.get(group_code)
        if not session or login not in session.clients:
            return
        client = session.clients[login]
        client.last_seen = datetime.now(timezone.utc)
        if active_window is not None:
            client.active_window = active_window
        if last_thumb_at is not None:
            client.last_thumb_at = last_thumb_at
        if ip_address is not None:
            client.ip_address = ip_address
        self._save_to_disk()

    def get_client_directives(self, group_code: str, login: str) -> Optional[dict]:
        """
        Retourne les directives pour un client spécifique.
        Inclut capture_now individuel si positionné.
        """
        session = self.get_active_session(group_code)
        if not session:
            return None

        directives = dict(session.directives)
        client = session.clients.get(login)
        if client and client.capture_now:
            directives["capture_now"] = True
            client.capture_now = False  # Reset après lecture
            self._save_to_disk()

        return directives

    def set_capture_now(self, group_code: str, login: str) -> bool:
        """Positionne capture_now pour un client spécifique."""
        session = self.get_active_session(group_code)
        if not session or login not in session.clients:
            return False
        session.clients[login].capture_now = True
        self._save_to_disk()
        return True

    def update_directives(self, group_code: str, directives: dict) -> bool:
        """Met à jour les directives globales d'une session."""
        session = self.get_active_session(group_code)
        if not session:
            return False
        session.directives.update(directives)
        self._save_to_disk()
        logger.info(f"Directives updated for session {group_code}")
        return True

    # ── Nettoyage ────────────────────────────────────────────────

    def get_sessions_to_cleanup(self, hours_after_close: int = 24) -> list[Session]:
        """Retourne les sessions fermées depuis plus de X heures, à nettoyer."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_after_close)
        return [
            s for s in self.sessions.values()
            if not s.is_active and s.expires_at < cutoff
        ]
