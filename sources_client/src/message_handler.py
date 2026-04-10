"""
message_handler.py — Gestion des messages serveur → client.

Affiche des popups tkinter ou des notifications tray selon le type.
Déduplique les messages via leur id unique.
"""

import logging
import threading
import tkinter as tk
from tkinter import ttk

logger = logging.getLogger(__name__)

# Try plyer for tray notifications
try:
    from plyer import notification as plyer_notification
    PLYER_AVAILABLE = True
except ImportError:
    PLYER_AVAILABLE = False
    logger.warning("plyer not available, tray notifications disabled.")


# Couleurs par type de message
MESSAGE_STYLES = {
    "info": {
        "bg": "#ffffff",
        "fg": "#333333",
        "accent": "#3498db",
        "icon": "ℹ",
        "title": "Information",
    },
    "warning": {
        "bg": "#fff3e0",
        "fg": "#333333",
        "accent": "#ff9800",
        "icon": "⚠",
        "title": "Avertissement",
    },
    "alert": {
        "bg": "#ffebee",
        "fg": "#333333",
        "accent": "#f44336",
        "icon": "✖",
        "title": "Alerte",
    },
}


class MessageHandler:
    """
    Gère l'affichage des messages reçus depuis le serveur.
    Déduplique via _last_displayed_id.
    """

    def __init__(self):
        self._last_displayed_id: str | None = None

    def handle(self, message: dict | None):
        """
        Traite un message reçu du serveur.

        Args:
            message: Dict avec id, text, type, display, duration_s.
                     None pour ne rien faire.
        """
        if message is None:
            return

        msg_id = message.get("id")
        if not msg_id:
            return

        # Déduplication
        if msg_id == self._last_displayed_id:
            return

        self._last_displayed_id = msg_id

        display = message.get("display", "popup")
        if display == "tray":
            self._show_tray_notification(message)
        else:
            self._show_popup(message)

    def _show_popup(self, message: dict):
        """
        Affiche un popup tkinter non bloquant.
        Exécuté dans un thread séparé pour ne pas bloquer la boucle principale.
        """
        thread = threading.Thread(
            target=self._popup_thread,
            args=(message,),
            daemon=True,
        )
        thread.start()

    def _popup_thread(self, message: dict):
        """Thread d'affichage du popup tkinter."""
        try:
            msg_type = message.get("type", "info")
            style = MESSAGE_STYLES.get(msg_type, MESSAGE_STYLES["info"])
            text = message.get("text", "")
            duration_s = message.get("duration_s", 0)

            root = tk.Tk()
            root.title(f"Supervision — {style['title']}")
            root.configure(bg=style["bg"])
            root.attributes("-topmost", True)
            root.resizable(False, False)

            # Centrer la fenêtre
            width, height = 420, 220
            screen_w = root.winfo_screenwidth()
            screen_h = root.winfo_screenheight()
            x = (screen_w - width) // 2
            y = (screen_h - height) // 2
            root.geometry(f"{width}x{height}+{x}+{y}")

            # Barre d'accent en haut
            accent_bar = tk.Frame(root, bg=style["accent"], height=4)
            accent_bar.pack(fill="x")

            # Contenu
            content = tk.Frame(root, bg=style["bg"], padx=20, pady=15)
            content.pack(fill="both", expand=True)

            # Icône + titre
            header = tk.Frame(content, bg=style["bg"])
            header.pack(fill="x", pady=(0, 10))

            icon_label = tk.Label(
                header, text=style["icon"],
                font=("Segoe UI", 24),
                bg=style["bg"], fg=style["accent"],
            )
            icon_label.pack(side="left")

            title_label = tk.Label(
                header, text=style["title"],
                font=("Segoe UI", 14, "bold"),
                bg=style["bg"], fg=style["fg"],
            )
            title_label.pack(side="left", padx=(10, 0))

            # Texte du message
            msg_label = tk.Label(
                content, text=text,
                font=("Segoe UI", 11),
                bg=style["bg"], fg=style["fg"],
                wraplength=380, justify="left",
                anchor="nw",
            )
            msg_label.pack(fill="both", expand=True, pady=(0, 10))

            # Bouton fermer (si durée = 0)
            if duration_s == 0:
                btn = tk.Button(
                    content, text="Fermer",
                    font=("Segoe UI", 10),
                    bg=style["accent"], fg="white",
                    relief="flat", padx=20, pady=5,
                    cursor="hand2",
                    command=root.destroy,
                )
                btn.pack(pady=(5, 0))

            # Fermeture automatique
            if duration_s > 0:
                root.after(duration_s * 1000, root.destroy)

            root.protocol("WM_DELETE_WINDOW", root.destroy)
            root.mainloop()

        except Exception as e:
            logger.error(f"Failed to show popup: {e}")

    def _show_tray_notification(self, message: dict):
        """Affiche une notification système via plyer."""
        if not PLYER_AVAILABLE:
            logger.warning("Cannot show tray notification: plyer not available.")
            # Fallback to popup
            self._show_popup(message)
            return

        try:
            plyer_notification.notify(
                title="Supervision",
                message=message.get("text", ""),
                timeout=5,
            )
            logger.info(f"Tray notification displayed: {message.get('id')}")
        except Exception as e:
            logger.error(f"Failed to show tray notification: {e}")
            # Fallback to popup
            self._show_popup(message)
