"""
auth.py — Définition de l'authentification pour le serveur de supervision.
Ce module gère deux types d'authentification :
1. Pour le Professeur (Interface Web) : Utilisation d'un cookie sécurisé et signé (via itsdangerous).
2. Pour les Clients (Élèves) : Utilisation d'un token "Bearer" envoyé dans l'en-tête (Header) "Authorization".
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

# ── Configuration Globale ────────────────────────────────────────────────

# Récupération des comptes professeurs depuis les variables d'environnement.
# Si aucune variable n'est définie, un compte par défaut (admin:password123) est utilisé.
# Le format attendu pour la variable est "utilisateur1:motdepasse1,utilisateur2:motdepasse2"
TEACHERS_ENV = os.environ.get("TEACHERS", "admin:password123")
TEACHERS: dict[str, str] = {}
for pair in TEACHERS_ENV.split(","):
    pair = pair.strip()
    if ":" in pair:
        user, pwd = pair.split(":", 1)
        TEACHERS[user.strip()] = pwd.strip()

# Token d'authentification fallback pour les clients (élèves) si une session spécifique ne fournit pas de token.
CLIENT_AUTH_TOKEN = os.environ.get("CLIENT_AUTH_TOKEN", "supervision-default-token")

# Clé secrète utilisée par le serveur pour signer les cookies cryptographiquement.
# En cas d'absence, une clé générée aléatoirement à chaque démarrage est utilisée.
SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_hex(32))
COOKIE_NAME = "supervision_session"
COOKIE_MAX_AGE = 8 * 3600  # Durée de vie maximale du cookie : 8 heures (une journée de cours)

# Initialisation du sérialiseur qui va générer et vérifier les cookies
serializer = URLSafeTimedSerializer(SECRET_KEY)


# ── Authentification Professeur (Gestion des Cookies) ─────────────────────────

def authenticate_teacher(username: str, password: str) -> bool:
    """
    Vérifie si les identifiants fournis (login / mot de passe) par un professeur sont valides.
    Retourne True en cas de succès, False sinon.
    """
    expected = TEACHERS.get(username)
    if expected is None:
        return False
    # On utilise 'compare_digest' pour empêcher les attaques par analyse temporelle (timing attacks)
    return secrets.compare_digest(expected, password)


def create_session_cookie(username: str) -> str:
    """
    Génère un cookie cryptographiquement signé contenant le nom d'utilisateur du professeur
    et un horodatage (timestamp) du moment de la connexion.
    """
    return serializer.dumps({"user": username, "ts": datetime.utcnow().isoformat()})


def verify_session_cookie(cookie_value: str) -> str | None:
    """
    Vérifie que le cookie fourni est valide, n'a pas été altéré et n'a pas expiré.
    Retourne le nom d'utilisateur (username) si tout est correct, sinon retourne None.
    """
    try:
        data = serializer.loads(cookie_value, max_age=COOKIE_MAX_AGE)
        return data.get("user")
    except (BadSignature, SignatureExpired):
        # La signature est invalide ou le cookie est trop vieux
        return None


def get_teacher_from_request(request: Request) -> str | None:
    """
    Parcourt la requête HTTP (FastAPI Request) pour extraire et valider le cookie de session.
    """
    cookie = request.cookies.get(COOKIE_NAME)
    if not cookie:
        return None
    return verify_session_cookie(cookie)


def require_teacher(request: Request) -> str:
    """
    Exige la présence d'une authentification valide pour le professeur.
    À utiliser comme dépendance (Dependency) dans les routes FastAPI protégeant le tableau de bord.
    Lève une erreur HTTP 401 si le professeur n'est pas identifié.
    """
    teacher_id = get_teacher_from_request(request)
    if not teacher_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return teacher_id


# ── Authentification Client (Communication API via Token Bearer) ───────────────────────

def verify_client_token(request: Request, expected_token: str = None) -> bool:
    """
    Vérifie le jeton d'autorisation fourni par le programme de l'élève (client).
    Le jeton doit être passé dans l'en-tête (header) HTTP 'Authorization' sous la forme 'Bearer <token>'.
    
    Args:
        request: La requête FastAPI entrante.
        expected_token: Le token attendu pour la session courante. Si absent, le token par défaut est vérifié.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return False
    
    token = auth_header[7:]  # Extrait le jeton situé après "Bearer "
    target = expected_token if expected_token else CLIENT_AUTH_TOKEN
    
    return secrets.compare_digest(token, target)


def require_client_token(request: Request, expected_token: str = None):
    """
    Protège les "endpoints" de l'API appelés par le programme élève (ex: envoi de capture d'écran).
    Lève une erreur HTTP 401 si le client n'envoie pas le bon mot de passe (token).
    """
    if not verify_client_token(request, expected_token):
        raise HTTPException(status_code=401, detail="Invalid or missing auth token")
