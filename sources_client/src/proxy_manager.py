"""
proxy_manager.py — Blocage internet commandé par le serveur.

Gère le proxy système Windows (HKCU) et les profils Firefox
pour bloquer/autoriser l'accès internet via un proxy fictif.

Note: Ce module utilise uniquement des APIs Windows (winreg, ctypes).
Sur d'autres OS, les opérations sont simulées en mode no-op.
"""

import os
import re
import glob
import logging
import platform

logger = logging.getLogger(__name__)

# Constantes proxy
PROXY_HOST = "127.0.0.1"
PROXY_PORT = 9999
PROXY_SERVER = f"{PROXY_HOST}:{PROXY_PORT}"

# Détection OS
IS_WINDOWS = platform.system() == "Windows"

if IS_WINDOWS:
    import winreg
    import ctypes

# Clé registre Internet Settings
INTERNET_SETTINGS_KEY = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"

# Option pour propager les changements sans reboot
INTERNET_OPTION_SETTINGS_CHANGED = 39
INTERNET_OPTION_REFRESH = 37


class ProxyManager:
    """
    Gère le blocage internet via proxy système et Firefox.
    Sauvegarde l'état original au démarrage, le restaure à la fermeture.
    """

    def __init__(self, supervision_hostname: str):
        """
        Args:
            supervision_hostname: Hostname du serveur de supervision
                                 (toujours exclu du proxy).
        """
        self.supervision_hostname = supervision_hostname
        self.is_blocking = False
        self.current_whitelist = []

        # État original sauvegardé au démarrage
        self._original_proxy_enable = 0
        self._original_proxy_server = ""
        self._original_proxy_override = ""
        self._original_firefox_proxy_type = None

        if IS_WINDOWS:
            self._save_original_state()
        else:
            logger.info("ProxyManager: Not on Windows, operating in no-op mode.")

    # ── Sauvegarde état original ─────────────────────────────────

    def _save_original_state(self):
        """Sauvegarde l'état proxy HKCU actuel."""
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS_KEY) as key:
                try:
                    self._original_proxy_enable, _ = winreg.QueryValueEx(key, "ProxyEnable")
                except FileNotFoundError:
                    self._original_proxy_enable = 0

                try:
                    self._original_proxy_server, _ = winreg.QueryValueEx(key, "ProxyServer")
                except FileNotFoundError:
                    self._original_proxy_server = ""

                try:
                    self._original_proxy_override, _ = winreg.QueryValueEx(key, "ProxyOverride")
                except FileNotFoundError:
                    self._original_proxy_override = ""

            logger.info(
                f"Proxy state saved: enable={self._original_proxy_enable}, "
                f"server='{self._original_proxy_server}', "
                f"override='{self._original_proxy_override}'"
            )
        except Exception as e:
            logger.error(f"Failed to save original proxy state: {e}")

    # ── Application des directives ────────────────────────────────

    def apply_directives(self, block: bool, whitelist: list[str]):
        """
        Applique ou désactive le blocage internet.

        Args:
            block: True pour activer le blocage, False pour le désactiver.
            whitelist: Liste de domaines autorisés (ignorée si block=False).
        """
        if not IS_WINDOWS:
            self.is_blocking = block
            self.current_whitelist = whitelist
            logger.info(f"ProxyManager (no-op): block={block}, whitelist={whitelist}")
            return

        if block:
            self._enable_block(whitelist)
        else:
            self._disable_block()

    def _enable_block(self, whitelist: list[str]):
        """Active le blocage internet via proxy."""
        # Toujours inclure le serveur de supervision dans la whitelist
        all_hosts = list(whitelist)
        if self.supervision_hostname and self.supervision_hostname not in all_hosts:
            all_hosts.append(self.supervision_hostname)

        # Construire ProxyOverride : "host1;host2;<local>"
        # Ajouter aussi le format IP brute pour garantir le bypass
        override_parts = list(all_hosts)
        # S'assurer que l'IP est aussi sous forme de pattern
        for h in list(override_parts):
            # Ajouter un pattern wildcard si c'est une IP (ex: 172.16.70.*)
            parts = h.split('.')
            if len(parts) == 4 and all(p.isdigit() for p in parts):
                wildcard = '.'.join(parts[:3]) + '.*'
                if wildcard not in override_parts:
                    override_parts.append(wildcard)
        override_parts.append("<local>")
        proxy_override = ";".join(override_parts)

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS_KEY, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, PROXY_SERVER)
                winreg.SetValueEx(key, "ProxyOverride", 0, winreg.REG_SZ, proxy_override)

            # Propager sans reboot
            self._notify_system()

            self.is_blocking = True
            self.current_whitelist = whitelist
            logger.info(f"Internet blocked. Whitelist: {all_hosts}")

        except Exception as e:
            logger.error(f"Failed to enable proxy block: {e}")

        # Firefox
        self._apply_firefox_proxy(block=True, whitelist=all_hosts)

    def _disable_block(self):
        """Désactive le blocage (ProxyEnable=0)."""
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS_KEY, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)

            self._notify_system()
            self.is_blocking = False
            self.current_whitelist = []
            logger.info("Internet unblocked (proxy disabled).")

        except Exception as e:
            logger.error(f"Failed to disable proxy block: {e}")

        # Firefox : proxy.type = 5 (system default)
        self._apply_firefox_proxy(block=False, whitelist=[])

    def _notify_system(self):
        """Propage les changements proxy au système via InternetSetOptionW."""
        try:
            internet_set_option = ctypes.windll.wininet.InternetSetOptionW
            internet_set_option(0, INTERNET_OPTION_SETTINGS_CHANGED, 0, 0)
            internet_set_option(0, INTERNET_OPTION_REFRESH, 0, 0)
        except Exception as e:
            logger.warning(f"Failed to notify system of proxy change: {e}")

    # ── Firefox ──────────────────────────────────────────────────

    def _get_firefox_profiles(self) -> list[str]:
        """Retourne les chemins des profils Firefox."""
        profiles_dir = os.path.join(
            os.environ.get("APPDATA", ""), "Mozilla", "Firefox", "Profiles"
        )
        if not os.path.exists(profiles_dir):
            return []
        return glob.glob(os.path.join(profiles_dir, "*"))

    def _apply_firefox_proxy(self, block: bool, whitelist: list[str]):
        """Écrit les préférences proxy dans user.js de chaque profil Firefox."""
        profiles = self._get_firefox_profiles()
        if not profiles:
            logger.debug("No Firefox profiles found.")
            return

        for profile_dir in profiles:
            user_js = os.path.join(profile_dir, "user.js")
            try:
                if block:
                    no_proxies = ", ".join(whitelist)
                    lines = [
                        'user_pref("network.proxy.type", 1);\n',
                        f'user_pref("network.proxy.http", "{PROXY_HOST}");\n',
                        f'user_pref("network.proxy.http_port", {PROXY_PORT});\n',
                        f'user_pref("network.proxy.ssl", "{PROXY_HOST}");\n',
                        f'user_pref("network.proxy.ssl_port", {PROXY_PORT});\n',
                        f'user_pref("network.proxy.no_proxies_on", "{no_proxies}");\n',
                    ]
                else:
                    lines = [
                        'user_pref("network.proxy.type", 5);\n',
                    ]

                # Lire le user.js existant et remplacer les lignes proxy
                existing_lines = []
                if os.path.exists(user_js):
                    with open(user_js, "r", encoding="utf-8") as f:
                        existing_lines = f.readlines()

                # Filtrer les anciennes lignes proxy
                proxy_keys = [
                    "network.proxy.type",
                    "network.proxy.http",
                    "network.proxy.http_port",
                    "network.proxy.ssl",
                    "network.proxy.ssl_port",
                    "network.proxy.no_proxies_on",
                ]
                filtered = [
                    l for l in existing_lines
                    if not any(k in l for k in proxy_keys)
                ]

                with open(user_js, "w", encoding="utf-8") as f:
                    f.writelines(filtered)
                    f.writelines(lines)

                logger.debug(f"Firefox proxy updated in {profile_dir}")

            except Exception as e:
                logger.warning(f"Failed to update Firefox profile {profile_dir}: {e}")

    # ── Restauration ─────────────────────────────────────────────

    def restore_original(self):
        """Restaure EXACTEMENT l'état proxy sauvegardé au démarrage."""
        if not IS_WINDOWS:
            self.is_blocking = False
            logger.info("ProxyManager (no-op): restored to original state.")
            return

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS_KEY, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, self._original_proxy_enable)
                winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, self._original_proxy_server)
                winreg.SetValueEx(key, "ProxyOverride", 0, winreg.REG_SZ, self._original_proxy_override)

            self._notify_system()
            self.is_blocking = False
            logger.info("Proxy state restored to original.")

        except Exception as e:
            logger.error(f"Failed to restore original proxy state: {e}")

        # Firefox : remettre en mode système
        self._apply_firefox_proxy(block=False, whitelist=[])

    # ── Watchdog ─────────────────────────────────────────────────

    def check_and_reapply(self):
        """
        Vérifie que le proxy HKCU est toujours correctement configuré.
        Si un utilisateur l'a modifié, réapplique le blocage.
        Appelée toutes les secondes depuis le watchdog main.
        """
        if not IS_WINDOWS or not self.is_blocking:
            return

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS_KEY) as key:
                try:
                    current_enable, _ = winreg.QueryValueEx(key, "ProxyEnable")
                except FileNotFoundError:
                    current_enable = 0

                try:
                    current_server, _ = winreg.QueryValueEx(key, "ProxyServer")
                except FileNotFoundError:
                    current_server = ""

            if current_enable != 1 or current_server != PROXY_SERVER:
                logger.warning("Proxy settings altered! Reapplying block.")
                self._enable_block(self.current_whitelist)

        except Exception as e:
            logger.error(f"Watchdog check failed: {e}")

    # ── Whitelist helper ─────────────────────────────────────────

    def add_to_whitelist(self, hostname: str):
        """Ajoute un hostname à la whitelist et réapplique si blocage actif."""
        if hostname not in self.current_whitelist:
            self.current_whitelist.append(hostname)
            if self.is_blocking and IS_WINDOWS:
                self._enable_block(self.current_whitelist)
