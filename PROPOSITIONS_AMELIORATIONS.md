# 📋 Propositions d'amélioration — Supervision COMEDU

---

## 1. Fenêtre d'interaction au clic gauche sur l'icône tray

### Contexte

Actuellement, l'élève doit effectuer un **clic droit** sur l'icône de la barre des tâches pour accéder au menu contextuel de Supervision. Ce comportement n'est pas intuitif pour la majorité des utilisateurs Windows, qui s'attendent à interagir avec un **clic gauche**.

Le menu contextuel actuel (clic droit) affiche uniquement :
- Le statut de connexion (texte brut)
- La taille de la file d'attente
- "Force Upload" / "Quit"

### Objectif

Permettre à l'élève d'**ouvrir une fenêtre d'information** via un **clic gauche** sur l'icône dans la barre des tâches, offrant une interface plus riche et intuitive.

### Description technique

#### 1. Capturer le clic gauche via `pystray`

La bibliothèque `pystray` (déjà utilisée) expose un paramètre **`on_activate`** dans le constructeur `pystray.Icon()`. Ce callback est déclenché lors d'un clic gauche (ou double-clic selon le backend Windows).

```python
# Avant (actuel)
self.icon = pystray.Icon("Supervision", icon_image, "Supervision", menu)

# Après (proposé)
self.icon = pystray.Icon(
    "Supervision", icon_image, "Supervision", menu,
    on_activate=self._on_left_click   # ← clic gauche
)
```

#### 2. Nouvelle classe `StatusPopup`

Créer une classe `StatusPopup` dans `ui.py` qui affiche une **fenêtre tkinter** positionnée au-dessus de la barre des tâches, à la manière d'un applet Windows natif.

**Contenu de la fenêtre :**

| Élément | Description |
|---------|-------------|
| 🟢/🔴 Indicateur | Pastille colorée indiquant l'état de connexion |
| Statut texte | "Connecté", "Hors-ligne", "Erreur", etc. |
| 👤 Identité | Prénom/nom de l'élève connecté |
| 📡 Session | Code groupe actif (ex: `AB12`) |
| 📸 Dernière capture | Horodatage de la dernière capture envoyée |
| 📊 File d'attente | Nombre de captures en attente d'envoi |
| 🌐 Internet | État du blocage internet (actif/inactif + sites autorisés) |
| Bouton "Forcer l'envoi" | Déclenche une capture immédiate |
| Bouton "Quitter" | Ferme proprement le client |

**Comportement de la fenêtre :**
- Apparaît au-dessus de la barre des tâches (coin inférieur droit)
- Se ferme automatiquement en cliquant ailleurs (perte de focus via `<FocusOut>`)
- Se ferme si on reclique sur l'icône tray (toggle)
- N'apparaît pas dans la barre des tâches elle-même (`root.overrideredirect(True)`)
- Style sombre cohérent avec la fenêtre de connexion (`#1a1a2e`)

#### 3. Positionnement automatique

```python
def _position_near_tray(self, root, width=300, height=350):
    """Positionne la fenêtre au-dessus de la zone de notification Windows."""
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    # Coin inférieur droit, au-dessus de la barre des tâches (~48px)
    x = screen_w - width - 12
    y = screen_h - height - 60
    root.geometry(f"{width}x{height}+{x}+{y}")
```

#### 4. Conservation du clic droit

Le menu contextuel actuel (clic droit) reste fonctionnel en parallèle, avec les options existantes. Il sert de raccourci rapide pour quitter, sans avoir à ouvrir la fenêtre complète.

### Maquette visuelle

```
┌──────────────────────────────┐
│  📡 Supervision              │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│                              │
│  ● Connecté                  │
│                              │
│  👤  Jean Dupont             │
│  📡  Groupe : AB12           │
│  📸  Dernière capture : 14:32│
│  📊  File d'attente : 0      │
│  🌐  Internet : ✅ autorisé  │
│                              │
│  ┌────────────┐ ┌──────────┐ │
│  │ 📤 Envoyer │ │ ✖ Quitter│ │
│  └────────────┘ └──────────┘ │
└──────────────────────────────┘
```

### Fichiers impactés

| Fichier | Modification |
|---------|-------------|
| `sources_client/src/ui.py` | Ajout de la classe `StatusPopup` (~100 lignes) + modification de `SupervisionUI` pour ajouter `on_activate` et stocker les données d'état |
| `sources_client/src/main.py` | Aucune modification nécessaire — l'interface publique de `SupervisionUI` ne change pas |

### Dépendances

Aucune nouvelle dépendance. Utilise uniquement :
- `pystray` (déjà présent) — callback `on_activate`
- `tkinter` (déjà présent) — fenêtre popup
- `PIL` (déjà présent) — icône tray

### Complexité estimée

- **Effort** : ~2h de développement + tests
- **Risque** : Faible — n'impacte pas la boucle principale ni le réseau
- **Rétro-compatibilité** : Totale — le clic droit continue de fonctionner

### Priorité suggérée

⭐⭐⭐ **Moyenne-haute** — Amélioration d'ergonomie significative pour les élèves, faible effort de développement, aucun risque sur le fonctionnement existant.

---

*Document mis à jour le 10/04/2026*
