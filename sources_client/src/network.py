"""
network.py — Communications HTTP client → serveur.

Toutes les requêtes incluent :
- Authorization: Bearer <auth_token>
- group_code dans le body multipart
- Gestion des codes HTTP (401, 404, 409, 410)
- Certificate pinning (vérifie le fingerprint SHA256 du certificat serveur)

Retourne les directives serveur (dict) ou un code d'erreur (str).
"""

import httpx
import logging
import os
import ssl
import hashlib
import socket
from urllib.parse import urlparse
from datetime import datetime

logger = logging.getLogger(__name__)

# Cache du résultat de vérification pour éviter de vérifier à chaque requête
_pinning_verified = False


def _verify_cert_fingerprint(config: dict) -> bool:
    """
    Vérifie le fingerprint SHA256 du certificat TLS du serveur.
    Retourne True si OK ou si pas de fingerprint configuré.
    Lève une exception si le fingerprint ne correspond pas.
    """
    global _pinning_verified
    if _pinning_verified:
        return True

    expected_fp = config.get('cert_fingerprint', '').strip()
    if not expected_fp:
        logger.debug("No cert_fingerprint configured — pinning disabled.")
        _pinning_verified = True
        return True

    server_url = config.get('server_url', '')
    parsed = urlparse(server_url)
    host = parsed.hostname
    port = parsed.port or 443

    try:
        # Connexion TLS brute pour récupérer le certificat
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        with socket.create_connection((host, port), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert_der = ssock.getpeercert(binary_form=True)

        actual_fp = hashlib.sha256(cert_der).hexdigest()

        if actual_fp.lower() != expected_fp.lower():
            logger.critical(
                f"CERTIFICATE PINNING FAILED!\n"
                f"  Expected: {expected_fp}\n"
                f"  Got:      {actual_fp}\n"
                f"  Server:   {host}:{port}\n"
                f"  This may indicate a man-in-the-middle attack or a rogue server."
            )
            raise SecurityError(
                f"Certificate fingerprint mismatch — refusing to connect to {host}:{port}"
            )

        logger.info(f"Certificate pinning OK — fingerprint verified for {host}:{port}")
        _pinning_verified = True
        return True

    except SecurityError:
        raise
    except Exception as e:
        logger.error(f"Certificate pinning check failed: {e}")
        # En cas d'erreur de connexion, on refuse (sécurité par défaut)
        raise SecurityError(f"Cannot verify server certificate: {e}")


class SecurityError(Exception):
    """Erreur de sécurité — le serveur n'est pas vérifié."""
    pass


def _get_ssl_verify(config: dict):
    """Retourne le paramètre verify pour httpx."""
    if not config.get('verify_ssl', False):
        return False
    ca_path = config.get('ca_cert_path', '')
    if ca_path and os.path.exists(ca_path):
        return ca_path
    return True


def _get_headers(config: dict) -> dict:
    """Retourne les headers d'authentification."""
    headers = {}
    token = config.get('auth_token', '')
    if token:
        headers['Authorization'] = f'Bearer {token}'
    return headers


async def send_heartbeat(config: dict, login: str, group_code: str,
                         screenshot_path: str = None,
                         active_window: str = None) -> dict | str | None:
    """
    Envoie un heartbeat au serveur.

    Returns:
        dict: Directives du serveur (succès)
        str: Code d'erreur ("401", "404", "409", "410")
        None: Erreur réseau/timeout
    """
    url = f"{config['server_url'].rstrip('/')}{config['heartbeat_endpoint']}"
    timestamp = datetime.now().isoformat()

    data = {
        "login": login,
        "group_code": group_code,
        "timestamp": timestamp,
    }
    if active_window:
        data["active_window"] = active_window

    try:
        # Vérification certificate pinning (une seule fois, puis caché)
        _verify_cert_fingerprint(config)

        async with httpx.AsyncClient(
            verify=_get_ssl_verify(config),
            timeout=config.get('timeout_s', 10),
            trust_env=False,
        ) as client:
            files = {}
            if screenshot_path and os.path.exists(screenshot_path):
                with open(screenshot_path, "rb") as f:
                    files["screenshot"] = (
                        os.path.basename(screenshot_path),
                        f,
                        "image/png",
                    )
                    response = await client.post(
                        url, data=data, files=files,
                        headers=_get_headers(config),
                    )
            else:
                response = await client.post(
                    url, data=data,
                    headers=_get_headers(config),
                )

            # Gestion des codes HTTP
            if response.status_code == 200:
                logger.info("Heartbeat sent successfully.")
                try:
                    return response.json()
                except Exception:
                    return {}

            elif response.status_code == 401:
                logger.error("HTTP 401 — Invalid auth token.")
                return "401"

            elif response.status_code == 404:
                logger.error("HTTP 404 — Group code not found or expired.")
                return "404"

            elif response.status_code == 409:
                logger.error("HTTP 409 — Login already bound to another session.")
                return "409"

            elif response.status_code == 410:
                logger.error("HTTP 410 — Session closed by teacher.")
                return "410"

            else:
                logger.error(f"Heartbeat failed with HTTP {response.status_code}")
                return None

    except SecurityError as e:
        logger.critical(f"SECURITY: {e}")
        return "SECURITY_ERROR"
    except Exception as e:
        logger.error(f"Failed to send heartbeat: {e}")
        return None


async def upload_screenshot(config: dict, login: str, group_code: str,
                            screenshot_path: str,
                            timestamp: str = None) -> dict | str | None:
    """
    Upload un screenshot dédié au serveur.

    Returns:
        dict: Réponse serveur (succès)
        str: Code d'erreur ("401", "404", "409", "410")
        None: Erreur réseau/timeout
    """
    url = f"{config['server_url'].rstrip('/')}{config['upload_endpoint']}"
    if not timestamp:
        timestamp = datetime.now().isoformat()

    data = {
        "login": login,
        "group_code": group_code,
        "timestamp": timestamp,
    }

    if not os.path.exists(screenshot_path):
        logger.error(f"Screenshot path does not exist: {screenshot_path}")
        return None

    try:
        # Vérification certificate pinning
        _verify_cert_fingerprint(config)

        async with httpx.AsyncClient(
            verify=_get_ssl_verify(config),
            timeout=config.get('timeout_s', 10),
            trust_env=False,
        ) as client:
            with open(screenshot_path, "rb") as f:
                files = {
                    "screenshot": (
                        os.path.basename(screenshot_path),
                        f,
                        "image/png",
                    )
                }
                response = await client.post(
                    url, data=data, files=files,
                    headers=_get_headers(config),
                )

            if response.status_code == 200:
                logger.info(f"Screenshot uploaded: {screenshot_path}")
                try:
                    return response.json()
                except Exception:
                    return {}

            elif response.status_code == 401:
                logger.error("HTTP 401 — Invalid auth token.")
                return "401"

            elif response.status_code == 404:
                logger.error("HTTP 404 — Session/client not found.")
                return "404"

            elif response.status_code == 410:
                logger.error("HTTP 410 — Session closed.")
                return "410"

            else:
                logger.error(f"Upload failed with HTTP {response.status_code}")
                return None

    except SecurityError as e:
        logger.critical(f"SECURITY: {e}")
        return "SECURITY_ERROR"
    except Exception as e:
        logger.error(f"Failed to upload screenshot: {e}")
        return None
