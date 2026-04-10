"""
download.py — Génération de packages client téléchargeables.

Crée un ZIP en mémoire contenant Supervision.exe + config.ini pré-configuré
pour une session donnée.
"""

import io
import os
import ssl
import hashlib
import zipfile
import logging
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

# Clé de transport partagée pour le chiffrement du config.ini
TRANSPORT_KEY = b"QJAJk_l12tcFUPbMNccPjRc1MSaE8uDGyRt-WI_Uioo="

# Chemin vers l'exe client Windows
CLIENT_BINARIES_DIR = os.path.join(os.path.dirname(__file__), "client_binaries")
WINDOWS_EXE = os.path.join(CLIENT_BINARIES_DIR, "Supervision.exe")


def _get_cert_fingerprint() -> str:
    """
    Calcule le fingerprint SHA256 du certificat serveur (server.crt).
    Retourne le fingerprint en hexadécimal ou une chaîne vide si le cert n'existe pas.
    """
    cert_path = os.path.join(os.path.dirname(__file__), "server.crt")
    if not os.path.exists(cert_path):
        cert_path = "server.crt"
    if not os.path.exists(cert_path):
        logger.warning("server.crt not found — certificate pinning disabled")
        return ""
    try:
        # Lire le certificat PEM et extraire le DER pour le hash
        with open(cert_path, "rb") as f:
            pem_data = f.read()
        cert_der = ssl.PEM_cert_to_DER_cert(pem_data.decode("ascii"))
        fingerprint = hashlib.sha256(cert_der).hexdigest()
        logger.info(f"Server certificate fingerprint: {fingerprint}")
        return fingerprint
    except Exception as e:
        logger.error(f"Failed to compute certificate fingerprint: {e}")
        return ""


def generate_config_ini(server_url: str, auth_token: str, group_code: str, session_id: str) -> str:
    """
    Génère le contenu du fichier config.ini pré-configuré.

    Args:
        server_url: URL du serveur de supervision (ex: http://192.168.1.50:3001)
        auth_token: Token d'authentification client
        group_code: Code de la session (4 caractères)

    Returns:
        Contenu du config.ini en texte.
    """
    cert_fingerprint = _get_cert_fingerprint()

    return f"""[Settings]
server_url = {server_url}
heartbeat_endpoint = /heartbeat
upload_endpoint = /upload-screenshot
capture_interval_s = 15
heartbeat_interval_s = 10
max_heartbeat_failures = 10
temp_dir = ./temp_captures
max_local_storage_mb = 500
timeout_s = 10
verify_ssl = false
auth_token = {auth_token}
group_code = {group_code}
session_id = {session_id}
cert_fingerprint = {cert_fingerprint}

[RetryPolicy]
max_retries = 10
initial_backoff_s = 1
max_backoff_s = 60
"""


def create_windows_package(server_url: str, auth_token: str, group_code: str, session_id: str) -> io.BytesIO:
    """
    Crée un ZIP en mémoire contenant Supervision.exe + config.ini.

    Args:
        server_url: URL du serveur
        auth_token: Token client
        group_code: Code session

    Returns:
        BytesIO contenant le ZIP.

    Raises:
        FileNotFoundError: Si Supervision.exe n'existe pas.
    """
    if not os.path.exists(WINDOWS_EXE):
        raise FileNotFoundError(
            f"Client Windows non trouvé: {WINDOWS_EXE}. "
            "Compilez le client avec PyInstaller et placez-le dans server/client_binaries/"
        )

    config_text = generate_config_ini(server_url, auth_token, group_code, session_id)

    # Chiffrement intégral du config.ini
    from cryptography.fernet import Fernet
    fernet = Fernet(TRANSPORT_KEY)
    config_encrypted = fernet.encrypt(config_text.encode('utf-8'))

    # Créer le ZIP en mémoire
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # Ajouter l'exe
        zf.write(WINDOWS_EXE, "Supervision/Supervision.exe")

        # Ajouter le config.ini chiffré
        zf.writestr("Supervision/config.ini", config_encrypted)

        # Ajouter le certificat SSL server.crt
        cert_path = "server.crt"
        if os.path.exists(cert_path):
            zf.write(cert_path, "Supervision/server.crt")

        # Ajouter un README
        readme = f"""=== Supervision Client ===

1. Extraire ce dossier sur le bureau
2. Lancer Supervision.exe
3. Entrer votre prénom/nom dans la fenêtre
4. Le code session {group_code} est déjà configuré

Le client se connectera automatiquement au serveur : {server_url}

En cas de problème, contactez votre professeur.
"""
        zf.writestr("Supervision/LISEZMOI.txt", readme)

    zip_buffer.seek(0)
    zip_size = zip_buffer.getbuffer().nbytes
    logger.info(
        f"Windows package created for session {group_code} "
        f"({zip_size / 1024 / 1024:.1f} MB)"
    )
    return zip_buffer


def check_client_available() -> dict:
    """
    Vérifie la disponibilité des clients.

    Returns:
        Dict avec les plateformes disponibles.
    """
    result = {
        "windows": os.path.exists(WINDOWS_EXE),
    }
    if result["windows"]:
        result["windows_size_mb"] = round(
            os.path.getsize(WINDOWS_EXE) / 1024 / 1024, 1
        )
    return result
