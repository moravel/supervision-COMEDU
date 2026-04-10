"""
ui.py — Interface utilisateur client.

- Fenêtre de démarrage tkinter (saisie login + code groupe)
- Icône tray (pystray) pour le monitoring
"""

import logging
import threading
import os
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

# Try pystray
try:
    import pystray
    from pystray import MenuItem as item
    PYSTRAY_AVAILABLE = True
except ImportError:
    PYSTRAY_AVAILABLE = False
    logger.warning("pystray not available, falling back to console mode.")


class StartupWindow:
    """
    Fenêtre tkinter de démarrage pour saisir login et code groupe.
    Modale, centrée, non redimensionnable, toujours au premier plan.
    """

    def __init__(self, initial_login: str = ""):
        self.login = initial_login
        self.group_code = None
        self.error_message = None
        self._root = None

    def show(self) -> tuple[str, str] | None:
        """
        Affiche la fenêtre et attend la saisie.
        Returns: (login, group_code) ou None si fermée sans valider.
        """
        self._root = tk.Tk()
        self._root.title("Supervision — Connexion")
        self._root.resizable(False, False)
        self._root.attributes("-topmost", True)
        self._root.configure(bg="#1a1a2e")

        # Centrer
        width, height = 380, 320
        screen_w = self._root.winfo_screenwidth()
        screen_h = self._root.winfo_screenheight()
        x = (screen_w - width) // 2
        y = (screen_h - height) // 2
        self._root.geometry(f"{width}x{height}+{x}+{y}")

        # Style
        bg = "#1a1a2e"
        fg = "#e8e8f0"
        entry_bg = "#0f0f1a"
        accent = "#6c63ff"
        muted = "#8888aa"
        error_color = "#ff4757"

        # Titre
        tk.Label(
            self._root, text="📡 Supervision",
            font=("Segoe UI", 18, "bold"),
            bg=bg, fg=accent,
        ).pack(pady=(24, 4))

        tk.Label(
            self._root, text="Connexion élève",
            font=("Segoe UI", 10),
            bg=bg, fg=muted,
        ).pack(pady=(0, 16))

        # Champ login
        tk.Label(
            self._root, text="PRÉNOM / NOM",
            font=("Segoe UI", 8, "bold"),
            bg=bg, fg=muted, anchor="w",
        ).pack(fill="x", padx=40)

        self._login_entry = tk.Entry(
            self._root,
            font=("Segoe UI", 12),
            bg=entry_bg, fg=fg,
            insertbackground=fg,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground="#2a2a44",
            highlightcolor=accent,
        )
        self._login_entry.pack(fill="x", padx=40, pady=(4, 12), ipady=6)
        
        if self.login:
            self._login_entry.insert(0, self.login)

        # Champ code groupe
        tk.Label(
            self._root, text="CODE GROUPE (4 caractères)",
            font=("Segoe UI", 8, "bold"),
            bg=bg, fg=muted, anchor="w",
        ).pack(fill="x", padx=40)

        self._code_entry = tk.Entry(
            self._root,
            font=("Segoe UI", 16, "bold"),
            bg=entry_bg, fg=fg,
            insertbackground=fg,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground="#2a2a44",
            highlightcolor=accent,
            justify="center",
        )
        self._code_entry.pack(fill="x", padx=40, pady=(4, 8), ipady=4)

        # Uppercase auto
        def on_code_change(*args):
            current = self._code_entry.get()
            upper = current.upper()[:4]
            if current != upper:
                self._code_entry.delete(0, "end")
                self._code_entry.insert(0, upper)

        self._code_var = tk.StringVar()
        self._code_entry.configure(textvariable=self._code_var)
        self._code_var.trace_add("write", on_code_change)

        # Label erreur
        self._error_label = tk.Label(
            self._root, text="",
            font=("Segoe UI", 9),
            bg=bg, fg=error_color,
            wraplength=300,
        )
        self._error_label.pack(pady=(2, 4))

        # Bouton démarrer
        self._submit_btn = tk.Button(
            self._root, text="Démarrer",
            font=("Segoe UI", 11, "bold"),
            bg=accent, fg="white",
            relief="flat",
            cursor="hand2",
            padx=20, pady=6,
            command=self._on_submit,
        )
        self._submit_btn.pack(pady=(4, 16))

        # Bind Enter
        self._root.bind("<Return>", lambda e: self._on_submit())

        # Focus
        if not self.login:
            self._login_entry.focus_set()
        else:
            self._code_entry.focus_set()

        # Protocol fermeture
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._root.mainloop()

        if self.login and self.group_code:
            return (self.login, self.group_code)
        return None

    def _on_submit(self):
        login = self._login_entry.get().strip()
        code = self._code_entry.get().strip().upper()

        if not login:
            self._show_error("Veuillez saisir votre prénom / nom.")
            return

        if len(code) != 4:
            self._show_error("Le code groupe doit faire exactement 4 caractères.")
            return

        self.login = login
        self.group_code = code
        self._root.destroy()

    def _on_close(self):
        self.login = None
        self.group_code = None
        self._root.destroy()

    def _show_error(self, message: str):
        self._error_label.config(text=message)

    def show_server_error(self, error_code: str):
        """
        Affiche une erreur retournée par le serveur au premier heartbeat.
        Relance la fenêtre si 404, quitte si 409/410.
        """
        if error_code == "404":
            self.error_message = "Code groupe invalide ou expiré.\nVérifiez avec votre professeur."
            self.group_code = None
        elif error_code == "409":
            self.error_message = "Ce nom est déjà utilisé dans cette session."
        elif error_code == "410":
            self.error_message = "La session est terminée."
        else:
            self.error_message = f"Erreur serveur ({error_code})."


class SupervisionUI:
    """Icône dans la barre des tâches (tray icon)."""

    def __init__(self, on_force_upload=None, on_quit=None):
        self.on_force_upload = on_force_upload
        self.on_quit = on_quit
        self.icon = None
        self.status = "Initializing..."
        self.queue_size = 0

    def create_image(self, width, height, color1, color2):
        image = Image.new('RGB', (width, height), color1)
        dc = ImageDraw.Draw(image)
        dc.rectangle(
            (width // 4, height // 4, width * 3 // 4, height * 3 // 4),
            fill=color2,
        )
        return image

    def update_status(self, status, queue_size=None):
        self.status = status
        if queue_size is not None:
            self.queue_size = queue_size
        if self.icon:
            self.icon.title = f"Supervision: {self.status} (Queue: {self.queue_size})"

    def run(self):
        if not PYSTRAY_AVAILABLE:
            logger.info("Running in console mode. Use Ctrl+C to quit.")
            return

        icon_image = self.create_image(64, 64, 'blue', 'white')

        items = [
            item(lambda text: f"Status: {self.status}", lambda: None, enabled=False),
            item(lambda text: f"Queue: {self.queue_size}", lambda: None, enabled=False),
            pystray.Menu.SEPARATOR,
        ]

        if self.on_force_upload:
            items.append(item('Force Upload', self.on_force_upload))

        if self.on_quit:
            items.append(item('Quit', self.on_quit))

        menu = pystray.Menu(*items)
        self.icon = pystray.Icon("Supervision", icon_image, "Supervision", menu)
        self.icon.run()

    def stop(self):
        if self.icon:
            self.icon.stop()
