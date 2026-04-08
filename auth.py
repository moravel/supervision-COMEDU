"""
auth.py — Authentification pour le serveur de supervision.
- Professeur : cookie signé (itsdangerous)
- Client (élève) : token Bearer dans header Authorization
"""

import os
import logging
import hashlib
import secrets
from datetime import datetime, timedelta
from functools import wraps

from fastapi import Request, HTTPException, Response
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────

# Comptes professeurs depuis variables d'environnement
# Format: "user1:pass1,user2:pass2"
TEACHERS_ENV = os.environ.get("TEACHERS", "admin:password123")
TEACHERS: dict[str, str] = {}
for pair in TEACHERS_ENV.split(","):
    pair = pair.strip()
    if ":" in pair:
        user, pwd = pair.split(":", 1)
        TEACHERS[user.strip()] = pwd.strip()

# Token d'authentification pour les clients (élèves)
CLIENT_AUTH_TOKEN = os.environ.get("CLIENT_AUTH_TOKEN", "supervision-default-token")

# Clé secrète pour signer les cookies
SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_hex(32))
COOKIE_NAME = "supervision_session"
COOKIE_MAX_AGE = 8 * 3600  # 8 heures

serializer = URLSafeTimedSerializer(SECRET_KEY)


# ── Authentification Professeur (Cookie) ─────────────────────────

def authenticate_teacher(username: str, password: str) -> bool:
    """Vérifie les identifiants d'un professeur."""
    expected = TEACHERS.get(username)
    if expected is None:
        return False
    # Comparaison en temps constant pour éviter timing attacks
    return secrets.compare_digest(expected, password)


def create_session_cookie(username: str) -> str:
    """Crée un cookie signé contenant l'identifiant du professeur."""
    return serializer.dumps({"user": username, "ts": datetime.utcnow().isoformat()})


def verify_session_cookie(cookie_value: str) -> str | None:
    """
    Vérifie un cookie signé et retourne le username.
    Retourne None si invalide ou expiré.
    """
    try:
        data = serializer.loads(cookie_value, max_age=COOKIE_MAX_AGE)
        return data.get("user")
    except (BadSignature, SignatureExpired):
        return None


def get_teacher_from_request(request: Request) -> str | None:
    """Extrait le teacher_id depuis le cookie de la requête."""
    cookie = request.cookies.get(COOKIE_NAME)
    if not cookie:
        return None
    return verify_session_cookie(cookie)


def require_teacher(request: Request) -> str:
    """
    Vérifie l'authentification professeur. 
    Lève HTTPException 401 si non authentifié.
    Retourne le teacher_id.
    """
    teacher_id = get_teacher_from_request(request)
    if not teacher_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return teacher_id


# ── Authentification Client (Token Bearer) ───────────────────────

def verify_client_token(request: Request, expected_token: str = None) -> bool:
    """
    Vérifie le token Bearer dans le header Authorization.
    Si expected_token est fourni, utilise celui-ci, sinon utilise
    le CLIENT_AUTH_TOKEN par défaut.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return False
    token = auth_header[7:]
    target = expected_token if expected_token else CLIENT_AUTH_TOKEN
    return secrets.compare_digest(token, target)


def require_client_token(request: Request, expected_token: str = None):
    """
    Vérifie le token client.
    Lève HTTPException 401 si invalide.
    """
    if not verify_client_token(request, expected_token):
        raise HTTPException(status_code=401, detail="Invalid or missing auth token")
