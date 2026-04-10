"""
config.py — Chargement de la configuration client avec support Fernet.

Les valeurs sensibles (auth_token, server_url) peuvent être chiffrées
avec le préfixe "ENC:" et sont déchiffrées automatiquement au chargement.
La clé de chiffrement est dérivée du SID Windows de l'utilisateur courant.
"""

import os
import sys
import base64
import hashlib
import configparser
import logging
import platform

logger = logging.getLogger(__name__)

# Clé de transport partagée pour le déchiffrement initial du config.ini
TRANSPORT_KEY = b"QJAJk_l12tcFUPbMNccPjRc1MSaE8uDGyRt-WI_Uioo="

DEFAULT_CONFIG = {
    'server_url': 'http://localhost:3001',
    'heartbeat_endpoint': '/heartbeat',
    'upload_endpoint': '/upload-screenshot',
    'capture_interval_s': 15,
    'heartbeat_interval_s': 60,
    'max_heartbeat_failures': 3,
    'temp_dir': './temp_captures',
    'max_local_storage_mb': 500,
    'retry_policy': {
        'max_retries': 10,
        'initial_backoff_s': 1,
        'max_backoff_s': 60,
    },
    'timeout_s': 10,
    'verify_ssl': False,
    'auth_token': '',
    'ca_cert_path': 'server.crt',
    'cert_fingerprint': '',
    'group_code': '',
    'session_id': '',
    'login': '',
}


def _get_windows_sid() -> str:
    """Récupère le SID Windows de l'utilisateur courant."""
    if platform.system() != "Windows":
        # Fallback pour dev/test sur Linux
        return os.environ.get("USER", "fallback-sid")
    try:
        import subprocess
        result = subprocess.run(
            ["whoami", "/user"],
            capture_output=True, text=True, timeout=5,
        )
        # Dernière colonne de la sortie contient le SID
        sid = result.stdout.strip().split()[-1]
        return sid
    except Exception as e:
        logger.error(f"Failed to get Windows SID: {e}")
        return "fallback-sid"


def _get_fernet_key() -> bytes:
    """Dérive une clé Fernet à partir du SID Windows."""
    sid = _get_windows_sid()
    key = base64.urlsafe_b64encode(
        hashlib.sha256(sid.encode()).digest()
    )
    return key


def _decrypt_value(value: str) -> str:
    """
    Déchiffre une valeur préfixée "ENC:".
    Retourne la valeur originale si pas de préfixe.
    """
    if not value.startswith("ENC:"):
        return value

    try:
        from cryptography.fernet import Fernet
        fernet = Fernet(_get_fernet_key())
        encrypted = value[4:]  # Retirer "ENC:"
        decrypted = fernet.decrypt(encrypted.encode()).decode()
        return decrypted
    except ImportError:
        logger.error("cryptography package not installed. Cannot decrypt config values.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to decrypt config value: {e}")
        sys.exit(1)


def load_config(config_path='config.ini') -> dict:
    """
    Charge la configuration depuis config.ini.
    Les valeurs préfixées "ENC:" sont déchiffrées automatiquement.
    """
    config = DEFAULT_CONFIG.copy()
    config['retry_policy'] = DEFAULT_CONFIG['retry_policy'].copy()

    # Rechercher config.ini à côté de l'exécutable si non trouvé dans CWD
    if not os.path.exists(config_path):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        potential_path = os.path.join(exe_dir, "config.ini")
        if os.path.exists(potential_path):
            config_path = potential_path

    if os.path.exists(config_path):
        parser = configparser.ConfigParser()
        
        try:
            with open(config_path, 'rb') as f:
                raw_data = f.read()

            # Essayer de déchiffrer avec la TRANSPORT_KEY (Chiffrement intégral)
            from cryptography.fernet import Fernet
            fernet = Fernet(TRANSPORT_KEY)
            decrypted_data = fernet.decrypt(raw_data).decode('utf-8')
            parser.read_string(decrypted_data)
            logger.info("Configuration déchiffrée avec succès.")
        except Exception as e:
            # Fallback : essayer de lire tel quel (cas non chiffré)
            try:
                parser.read_file(open(config_path, 'r', encoding='utf-8'))
            except Exception as e2:
                logger.error(f"Fichier de configuration illisible ou invalide : {e2}")
                return config

        if 'Settings' in parser:
            s = parser['Settings']
            config['server_url'] = _decrypt_value(
                s.get('server_url', config['server_url'])
            )
            config['heartbeat_endpoint'] = s.get('heartbeat_endpoint', config['heartbeat_endpoint'])
            config['upload_endpoint'] = s.get('upload_endpoint', config['upload_endpoint'])
            config['capture_interval_s'] = s.getint('capture_interval_s', config['capture_interval_s'])
            config['heartbeat_interval_s'] = s.getint('heartbeat_interval_s', config['heartbeat_interval_s'])
            config['max_heartbeat_failures'] = s.getint('max_heartbeat_failures', config['max_heartbeat_failures'])
            config['temp_dir'] = s.get('temp_dir', config['temp_dir'])
            config['max_local_storage_mb'] = s.getint('max_local_storage_mb', config['max_local_storage_mb'])
            config['timeout_s'] = s.getint('timeout_s', config['timeout_s'])
            config['verify_ssl'] = s.getboolean('verify_ssl', config['verify_ssl'])
            config['auth_token'] = _decrypt_value(
                s.get('auth_token', config['auth_token'])
            )
            config['ca_cert_path'] = s.get('ca_cert_path', config['ca_cert_path'])
            config['cert_fingerprint'] = s.get('cert_fingerprint', config['cert_fingerprint'])
            config['group_code'] = s.get('group_code', config['group_code']).upper()
            config['session_id'] = s.get('session_id', config['session_id'])
            config['login'] = s.get('login', config['login'])

        if 'RetryPolicy' in parser:
            rp = parser['RetryPolicy']
            config['retry_policy']['max_retries'] = rp.getint('max_retries', config['retry_policy']['max_retries'])
            config['retry_policy']['initial_backoff_s'] = rp.getint('initial_backoff_s', config['retry_policy']['initial_backoff_s'])
            config['retry_policy']['max_backoff_s'] = rp.getint('max_backoff_s', config['retry_policy']['max_backoff_s'])

    # Résoudre chemin relatif temp_dir
    if not os.path.isabs(config['temp_dir']):
        config_dir = os.path.dirname(os.path.abspath(config_path))
        config['temp_dir'] = os.path.join(config_dir, config['temp_dir'])

    # Résoudre chemin relatif ca_cert_path
    if config['ca_cert_path'] and not os.path.isabs(config['ca_cert_path']):
        config_dir = os.path.dirname(os.path.abspath(config_path))
        config['ca_cert_path'] = os.path.join(config_dir, config['ca_cert_path'])

    # Créer temp_dir
    os.makedirs(config['temp_dir'], exist_ok=True)

    return config


def get_username():
    """Récupère le nom d'utilisateur Windows ou Linux."""
    return os.environ.get('USERNAME') or os.environ.get('USER') or 'unknown'


def _decrypt_value(value: str) -> str:
    """Décharge les anciennes valeurs chiffrées par SID si présentes."""
    if not value or not value.startswith("ENC:"):
        return value
    try:
        from cryptography.fernet import Fernet
        token = value[4:]
        # Clé dérivée du SID (ancien système)
        key = base64.urlsafe_b64encode(hashlib.sha256(_get_windows_sid().encode()).digest())
        fernet = Fernet(key)
        return fernet.decrypt(token.encode()).decode()
    except Exception:
        return value
