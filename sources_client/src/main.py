"""
main.py — Client de supervision scolaire.

Orchestration complète :
- Fenêtre de démarrage (login + code groupe)
- Heartbeat périodique avec directives serveur
- Capture d'écran périodique
- Gestion du proxy (blocage internet)
- Messages serveur (popup/tray)
- Ouverture d'URL commandée
- Capture à la demande
- Watchdog proxy
"""

import asyncio
import threading
import argparse
import logging
import os
import signal
import sys
import time
import webbrowser
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from logging.handlers import RotatingFileHandler
from urllib.parse import urlparse

from config import load_config, get_username
from capture import take_screenshot, generate_filename
from network import send_heartbeat, upload_screenshot
from queue_manager import QueueManager
from ui import SupervisionUI, StartupWindow
from proxy_manager import ProxyManager
from message_handler import MessageHandler

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ── Logging avec rotation ────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(
            "client.log",
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=3,
            encoding='utf-8',
        ),
    ],
)
logger = logging.getLogger("SupervisionClient")


class SupervisionClient:
    def __init__(self, config: dict, login: str, group_code: str, dry_run: bool = False):
        self.config = config
        self.login = login
        self.group_code = group_code.upper()
        self.dry_run = dry_run

        # Modules
        self.queue_manager = QueueManager(config)
        self.ui = SupervisionUI(on_force_upload=self.force_upload, on_quit=self.quit)

        # Proxy manager — extraire hostname du server_url
        parsed = urlparse(config['server_url'])
        supervision_hostname = parsed.hostname or "localhost"
        self.proxy_manager = ProxyManager(supervision_hostname)

        # Message handler
        self.message_handler = MessageHandler()

        # État
        self.running = True
        self.loop = None
        self.executor = ThreadPoolExecutor(max_workers=1)

        # Heartbeat failure counter
        self._consecutive_heartbeat_failures = 0
        self._max_failures = config.get('max_heartbeat_failures', 3)

        # Déduplication ouverture URL
        self._last_opened_url = None

    # ── Actions UI ───────────────────────────────────────────────

    async def force_upload(self, icon=None, item=None):
        logger.info("Manual upload triggered.")
        await self.capture_step()

    def quit(self, icon=None, item=None):
        logger.info("Quitting application...")
        # Restaurer l'état original du proxy
        self.proxy_manager.restore_original()
        self.running = False
        self.executor.shutdown(wait=False)
        if self.ui:
            self.ui.stop()

    # ── Capture ──────────────────────────────────────────────────

    async def capture_step(self):
        """Capture un screenshot et l'envoie ou le met en file."""
        temp_filename = generate_filename(self.config['temp_dir'])

        if self.dry_run:
            logger.info(f"[DRY-RUN] Would take screenshot: {temp_filename}")
            return

        try:
            screenshot_path = await self.loop.run_in_executor(
                self.executor, take_screenshot, temp_filename,
            )

            self.ui.update_status("Uploading...", self.queue_size)
            result = await upload_screenshot(
                self.config, self.login, self.group_code, screenshot_path,
            )

            if isinstance(result, dict):
                os.remove(screenshot_path)
                self.ui.update_status("Connected", self.queue_size)
            elif isinstance(result, str):
                # Code d'erreur HTTP
                await self._handle_http_error(result)
            else:
                # Erreur réseau → file d'attente
                self.queue_manager.add_to_queue(screenshot_path)
                self.ui.update_status("Offline", self.queue_size)

        except Exception as e:
            logger.error(f"Error in capture step: {e}")
            self.ui.update_status("Error", self.queue_size)

    @property
    def queue_size(self):
        return len(self.queue_manager.queue)

    # ── Gestion des directives serveur ───────────────────────────

    async def _apply_server_directives(self, directives):
        """
        Traite les directives reçues du serveur.

        Args:
            directives: dict (succès), str (erreur HTTP), ou None (erreur réseau).
        """
        if isinstance(directives, str):
            # Code d'erreur HTTP
            await self._handle_http_error(directives)
            return

        if directives is None:
            # Erreur réseau
            self._consecutive_heartbeat_failures += 1
            logger.warning(
                f"Heartbeat failure {self._consecutive_heartbeat_failures}/{self._max_failures}"
            )
            if self._consecutive_heartbeat_failures >= self._max_failures:
                await self._emergency_shutdown()
            return

        # Succès — reset compteur
        self._consecutive_heartbeat_failures = 0

        # 1. Proxy/blocage internet
        block = directives.get("block_internet", False)
        whitelist = directives.get("whitelist", [])
        await self.loop.run_in_executor(
            None, self.proxy_manager.apply_directives, block, whitelist,
        )

        # 2. Message
        await self._handle_message(directives)

        # 3. URL
        await self._handle_open_url(directives)

        # 4. Capture immédiate
        await self._handle_capture_now(directives)

    async def _handle_http_error(self, error_code: str):
        """Gère les erreurs HTTP fatales."""
        if error_code == "401":
            await self._emergency_shutdown()
        elif error_code == "404":
            logger.error("Group code invalid or expired.")
            self.ui.update_status("Error: Code invalide")
            await self.loop.run_in_executor(
                None, self.proxy_manager.restore_original,
            )
            self.running = False
            await asyncio.sleep(2)
            self.ui.stop()
        elif error_code == "409":
            logger.error("Login already bound to another session.")
            self.ui.update_status("Error: Login déjà utilisé")
            self.running = False
            await asyncio.sleep(2)
            self.ui.stop()
        elif error_code == "410":
            logger.info("Session closed by teacher.")
            self.ui.update_status("Session terminée")
            await self.loop.run_in_executor(
                None, self.proxy_manager.restore_original,
            )
            self.running = False
            await asyncio.sleep(2)
            self.ui.stop()

    async def _emergency_shutdown(self):
        """Arrêt d'urgence : restauration proxy + quit."""
        logger.critical("Emergency shutdown triggered.")
        await self.loop.run_in_executor(
            None, self.proxy_manager.restore_original,
        )
        self.running = False
        self.ui.update_status("Serveur perdu — arrêt")
        await asyncio.sleep(2)
        self.ui.stop()

    async def _handle_message(self, directives: dict):
        """Traite les messages serveur."""
        message = directives.get("message", None)
        await self.loop.run_in_executor(
            None, self.message_handler.handle, message,
        )

    async def _handle_open_url(self, directives: dict):
        """Traite les commandes d'ouverture d'URL."""
        open_url = directives.get("open_url", None)

        if open_url is None:
            self._last_opened_url = None
            return

        target = open_url.get("target", "all")
        if target != "all" and target != self.login:
            return

        url = open_url.get("url", "")
        if not url or url == self._last_opened_url:
            return

        # Si blocage actif, ajouter le hostname à la whitelist
        if self.proxy_manager.is_blocking:
            try:
                hostname = urlparse(url).hostname
                if hostname:
                    self.proxy_manager.add_to_whitelist(hostname)
            except Exception:
                pass

        self._last_opened_url = url
        await self.loop.run_in_executor(None, webbrowser.open, url)
        logger.info(f"URL ouverte sur ordre du serveur : {url}")

    async def _handle_capture_now(self, directives: dict):
        """Traite les demandes de capture immédiate."""
        if directives.get("capture_now", False):
            logger.info("Capture immédiate déclenchée par le serveur.")
            await self.capture_step()

    # ── Boucle principale ────────────────────────────────────────

    async def main_loop(self):
        self.loop = asyncio.get_running_loop()

        logger.info(f"Client started: login={self.login}, group_code={self.group_code}")
        self.ui.update_status("Connecting...", self.queue_size)

        # 1. Premier heartbeat avec capture initiale
        temp_filename = generate_filename(self.config['temp_dir'])
        init_screenshot = None
        if not self.dry_run:
            try:
                init_screenshot = await self.loop.run_in_executor(
                    self.executor, take_screenshot, temp_filename,
                )
            except Exception as e:
                logger.warning(f"Initial screenshot failed: {e}")

        # Obtenir la fenêtre active (Windows)
        active_window = self._get_active_window()

        directives = await send_heartbeat(
            self.config, self.login, self.group_code,
            screenshot_path=init_screenshot,
            active_window=active_window,
        )

        # Nettoyer screenshot initial
        if init_screenshot and os.path.exists(init_screenshot):
            try:
                os.remove(init_screenshot)
            except Exception:
                pass

        # Appliquer les directives initiales
        await self._apply_server_directives(directives)

        if not self.running:
            return

        self.ui.update_status("Connected", self.queue_size)

        # 2. Boucles de capture et heartbeat
        last_capture = time.time()
        last_heartbeat = time.time()
        capture_interval = self.config['capture_interval_s']
        heartbeat_interval = self.config.get('heartbeat_interval_s', 60)

        while self.running:
            now = time.time()

            # Capture périodique
            if now - last_capture >= capture_interval:
                await self.capture_step()
                last_capture = now

            # Heartbeat périodique (sans screenshot, juste pour directives)
            if now - last_heartbeat >= heartbeat_interval:
                active_window = self._get_active_window()
                directives = await send_heartbeat(
                    self.config, self.login, self.group_code,
                    active_window=active_window,
                )
                await self._apply_server_directives(directives)
                last_heartbeat = now

                if not self.running:
                    return

            # Traiter la file d'attente
            if not self.dry_run:
                await self.queue_manager.process_queue(
                    upload_screenshot, self.login, self.group_code,
                )

            # Watchdog proxy (toutes les secondes)
            await self.loop.run_in_executor(
                None, self.proxy_manager.check_and_reapply,
            )

            # Status UI
            status = "Connected" if self.queue_size == 0 else "Offline"
            self.ui.update_status(status, self.queue_size)

            await asyncio.sleep(1)

    def _get_active_window(self) -> str:
        """Retourne le titre de la fenêtre active (Windows)."""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            length = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value
        except Exception:
            return ""

    def run(self):
        # Start tray icon in separate thread
        ui_thread = threading.Thread(target=self.ui.run, daemon=True)
        ui_thread.start()

        try:
            asyncio.run(self.main_loop())
        except KeyboardInterrupt:
            self.quit()


# ══════════════════════════════════════════════════════════════════
# Point d'entrée
# ══════════════════════════════════════════════════════════════════

def main():
    # Déterminer le chemin de base
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    default_config = os.path.join(base_path, "config.ini")

    parser = argparse.ArgumentParser(description="Supervision Client")
    parser.add_argument("--config", default=default_config, help="Path to config file")
    parser.add_argument("--dry-run", action="store_true", help="Simulate capture and network")
    args = parser.parse_args()

    config = load_config(args.config)

    # ── Vérification CA cert ─────────────────────────────────────
    ca_path = config.get('ca_cert_path', '')
    if config.get('verify_ssl', False) and ca_path and not os.path.exists(ca_path):
        logger.critical(f"CA certificate not found: {ca_path}. Aborting.")
        sys.exit(1)

    # ── Obtenir login et group_code ──────────────────────────────
    login = config.get('login', '').strip()
    group_code = config.get('group_code', '').strip()

    # Auto-login si non défini
    if not login:
        login = get_username()
        logger.info(f"Auto-detected system login: {login}")

    if group_code:
        # Pré-configuré (cas du téléchargement via /join)
        logger.info(f"Using auto-configured login={login}, group_code={group_code}")
    else:
        # Fenêtre de démarrage
        startup = StartupWindow(initial_login=login)
        result = startup.show()
        if result is None:
            logger.info("Startup window closed without credentials. Exiting.")
            sys.exit(0)
        login, group_code = result

    # ── Démarrer le client ───────────────────────────────────────
    client = SupervisionClient(config, login, group_code, dry_run=args.dry_run)
    client.run()


if __name__ == "__main__":
    main()
