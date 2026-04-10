# Supervision Scolaire

Système de supervision en temps réel pour les salles de classe Windows.
Un professeur crée une session, obtient un code groupe, et supervise
les écrans de ses élèves via un tableau de bord web avec mur de miniatures.

---

## Architecture

```
┌───────────────────────────────────────────────────────────┐
│                    SERVEUR (Python/FastAPI)                │
│                                                           │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │  Sessions    │  │  Thumbnails  │  │   SSE Manager   │  │
│  │  Manager     │  │  (Pillow)    │  │   (temps réel)  │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬────────┘  │
│         │                 │                    │           │
│  ┌──────┴─────────────────┴────────────────────┴────────┐  │
│  │              FastAPI Application (app.py)             │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         │ Port 3001                        │
└─────────────────────────┼─────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          │               │               │
    ┌─────┴─────┐   ┌─────┴─────┐   ┌─────┴─────┐
    │  Client 1  │   │  Client 2  │   │  Client N  │
    │  (Élève)   │   │  (Élève)   │   │  (Élève)   │
    └───────────┘   └───────────┘   └───────────┘
```

### Modules serveur

| Module | Rôle |
|---|---|
| `app.py` | Application FastAPI, tous les endpoints, point d'entrée |
| `models.py` | Modèles de données (Session, ClientInfo) |
| `sessions.py` | Gestion sessions, codes groupes, liaison clients |
| `download.py` | Génération dynamique des packages ZIP (exe + config) |
| `thumbnail.py` | Génération miniatures JPEG avec Pillow |
| `sse.py` | Server-Sent Events pour le temps réel |
| `auth.py` | Authentification professeur (cookie) + client (token Bearer) |
| `cleanup.py` | Nettoyage planifié des fichiers 24h après fermeture |
| `templates/` | Pages HTML (login, sessions, dashboard, join) |
| `client_binaries/` | Stockage de l'exe compilé pour distribution |

### Modules client

| Module | Rôle |
|---|---|
| `main.py` | Orchestration : heartbeat, directives, proxy, messages |
| `config.py` | Chargement config.ini + déchiffrement Fernet |
| `network.py` | Communications HTTPS avec token + gestion codes HTTP |
| `capture.py` | Capture d'écran (mss) |
| `queue_manager.py` | File d'attente locale (mode hors ligne) |
| `ui.py` | Fenêtre de démarrage tkinter + icône tray |
| `proxy_manager.py` | Blocage internet (HKCU + Firefox) |
| `message_handler.py` | Popup/notification des messages serveur |
| `encrypt_config.py` | Script admin de chiffrement config |

---

## Flux de démarrage

```
1. Le prof se connecte à l'interface web (http://serveur:3001)
2. Il crée une session → code groupe généré (ex: AX7K)
3. Il communique le code aux élèves (oral, tableau)
4. Chaque élève accède à http://serveur:3001/join et saisit le code
5. L'élève télécharge un ZIP pré-configuré (exe + config.ini injecté)
6. L'élève extrait et lance **Supervision.exe**
7. Le serveur valide la connexion et le prof voit l'écran en temps réel
```

---

## Déploiement serveur

### Prérequis

- Docker + Docker Compose
- (Optionnel) OpenSSL pour la CA privée

### Génération CA privé (production)

```bash
# 1. Générer la CA (autorité de certification)
openssl req -x509 -newkey rsa:4096 -keyout ca.key \
  -out ca.crt -days 3650 -nodes -subj "/CN=SupervisionCA"

# 2. Générer le certificat serveur
openssl req -newkey rsa:4096 -keyout server.key \
  -out server.csr -nodes -subj "/CN=<server_hostname>"

# 3. Signer le certificat serveur avec la CA
openssl x509 -req -in server.csr -CA ca.crt \
  -CAkey ca.key -out server.crt -days 365

# Distribution :
#   ca.key         → ne quitte JAMAIS le poste administrateur
#   ca.crt         → distribué avec le client portable
#   server.crt+key → déployés sur le serveur
```

### Lancement Docker

```bash
cd server/
docker compose up -d --build
```

Le serveur est accessible sur le port **3001**.

### Compilation Windows depuis Linux (Wine)

Si vous développez sur Linux, vous pouvez recompiler le client Windows (`.exe`) via Wine :

```bash
# 1. Installer Python Windows dans Wine
wget https://www.python.org/ftp/python/3.12.3/python-3.12.3-amd64.exe
wine python-3.12.3-amd64.exe /quiet PrependPath=1

# 2. Installer les dépendances client sous Wine
wine python -m pip install pyinstaller mss pystray Pillow httpx plyer cryptography

# 3. Compiler l'exécutable
cd sources_client/
wine python -m PyInstaller --onefile --noconsole --name Supervision src/main.py --hidden-import pystray._win32 --collect-all mss --clean -y

# 4. Déployer l'exe sur le serveur pour le téléchargement /join
cp dist/Supervision.exe ../server/client_binaries/
```

---

## Déploiement client (via /join)

Le client n'a plus besoin d'être configuré manuellement par l'élève.

### Téléchargement automatisé
Les élèves se rendent sur `http://<ip-serveur>:3001/join`, entrent le code session, et cliquent sur **Télécharger**. Le serveur génère à la volée un fichier `config.ini` contenant l'URL du serveur et le code groupe, puis propose un ZIP contenant l'exécutable et sa configuration.

### Variables d'environnement

| Variable | Description | Défaut |
|---|---|---|
| `PORT` | Port du serveur | `3001` |
| `TEACHERS` | Comptes professeurs (format `user:pass,user2:pass2`) | `admin:password123` |
| `CLIENT_AUTH_TOKEN` | Token d'authentification des clients | `supervision-default-token` |
| `SECRET_KEY` | Clé secrète pour les cookies signés | Auto-généré |
| `UPLOADS_DIR` | Répertoire de stockage des captures | `uploads` |

### Configuration des comptes professeurs

Modifier la variable `TEACHERS` dans `docker-compose.yml` :

```yaml
environment:
  - TEACHERS=dupont:MotDePasse1,martin:MotDePasse2
```

---

## Déploiement client

### Structure du dossier client portable

```
supervision-client/
├── Supervision.exe     ← Exécutable PyInstaller
├── config.ini          ← Configuration
└── ca.crt              ← Certificat CA (production)
```

### Configuration config.ini

```ini
[Settings]
server_url = https://supervision.ecole.fr:3001
heartbeat_endpoint = /heartbeat
upload_endpoint = /upload-screenshot
capture_interval_s = 15
heartbeat_interval_s = 60
max_heartbeat_failures = 3
temp_dir = ./temp_captures
max_local_storage_mb = 500
timeout_s = 10
verify_ssl = true
auth_token = mon-token-secret
ca_cert_path = ca.crt
group_code =
login =

[RetryPolicy]
max_retries = 10
initial_backoff_s = 1
max_backoff_s = 60
```

### Cas 1 : Pré-configuré (group_code dans config.ini)

Si `login` et `group_code` sont renseignés dans config.ini, le client
se connecte directement sans afficher la fenêtre de saisie.

### Cas 2 : Saisie manuelle au lancement

Si `login` ou `group_code` sont vides, une fenêtre de connexion s'affiche
demandant le prénom/nom de l'élève et le code groupe.

### Chiffrement de la configuration (administrateur)

```bash
# Sur le poste cible, en tant qu'administrateur :
pip install cryptography

# Chiffrer les valeurs sensibles
python encrypt_config.py --config config.ini --fields auth_token,server_url

# Vérifier le chiffrement
python encrypt_config.py --config config.ini --fields auth_token,server_url --verify
```

Le chiffrement utilise Fernet avec une clé dérivée du SID Windows.
Les valeurs chiffrées sont préfixées `ENC:` et déchiffrées au chargement.

---

## Utilisation

### Procédure professeur

1. **Se connecter** à `http://serveur:3001` avec ses identifiants.
2. **Créer une session** → saisir un libellé → copier le code groupe (4 caractères).
3. **Projeter le code** aux élèves (affiché en grand, 96px).
4. **Superviser** via le mur de miniatures :
   - Miniatures actualisées en temps réel (SSE)
   - Bordure verte (<30s), orange (30s-2m), rouge (>2m)
   - Badges : 🟢 Actif, 🟡 Inactif, 🔴 Déconnecté
5. **Actions globales** :
   - 🔒 Bloquer internet (toggle + whitelist de domaines)
   - 💬 Envoyer un message (info/warning/alert)
   - 🌐 Ouvrir une URL sur tous les postes
   - 📸 Capturer tous les écrans immédiatement
6. **Actions individuelles** :
   - 📸 Capturer un écran spécifique
   - 🔍 Voir l'historique des captures (navigation ◀ ▶)
7. **Fermer la session** → les clients sont déconnectés proprement.

### Procédure élève

1. **Lancer** `Supervision.exe`.
2. **Saisir** son prénom/nom et le code groupe communiqué par le prof.
3. **Travailler** normalement — le client tourne en arrière-plan.
4. **Fin de session** — le client se ferme automatiquement quand le prof ferme la session.

---

## Référence technique

### Format JSON — Réponse heartbeat serveur

```json
{
  "block_internet": true,
  "whitelist": ["domaine1.com", "*.edu.fr"],
  "message": {
    "id": "msg_001",
    "text": "Texte affiché à l'utilisateur.",
    "type": "info",
    "display": "popup",
    "duration_s": 10
  },
  "open_url": {
    "url": "https://monent.fr/sujet.pdf",
    "target": "all"
  },
  "capture_now": false
}
```

### Endpoints serveur

#### Client → Serveur

| Méthode | Endpoint | Body | Réponse |
|---|---|---|---|
| POST | `/heartbeat` | `login`, `group_code`, `timestamp`, `active_window`, `screenshot` (multipart) | Directives JSON |
| POST | `/upload-screenshot` | `login`, `group_code`, `timestamp`, `screenshot` (multipart) | `{"success": true}` |

#### Professeur → Serveur

| Méthode | Endpoint | Body | Réponse |
|---|---|---|---|
| POST | `/login` | `username`, `password` | Redirect + cookie |
| POST | `/session/create` | `{"label": "...", "expires_in_hours": 8}` | `{"group_code": "AX7K", ...}` |
| POST | `/session/close` | `{"group_code": "AX7K"}` | `{"success": true}` |
| GET | `/session/{code}/clients` | — | Liste clients JSON |
| GET | `/session/{code}/directives` | — | Directives JSON |
| PUT | `/session/{code}/directives` | Directives JSON | `{"success": true}` |
| GET | `/session/{code}/thumbnails` | — | Liste miniatures JSON |
| GET | `/session/{code}/stream` | — | SSE stream |
| POST | `/session/{code}/client/{login}/capture` | — | `{"success": true}` |
| GET | `/media/{code}/{login}/thumb_latest.jpg` | — | Image JPEG |
| GET | `/media/{code}/{login}/latest.png` | — | Image PNG |
| GET | `/media/{code}/{login}/history` | — | Liste historique JSON |

### Codes HTTP — Comportement client

| Code | Signification | Action client |
|---|---|---|
| 200 | Succès | Traiter les directives normalement |
| 401 | Token invalide | `_emergency_shutdown()` |
| 404 | Code groupe invalide/expiré | Afficher erreur + quitter |
| 409 | Login déjà lié à une autre session | Afficher erreur + quitter |
| 410 | Session fermée par le prof | `restore_original()` + quitter |

### Stockage fichiers serveur

```
uploads/
└── {group_code}/
    └── {login}/
        ├── latest.png              ← Dernier screenshot original
        ├── thumb_latest.jpg        ← Miniature du dernier screenshot
        └── history/
            ├── 20260403_093214.png
            └── 20260403_093214_thumb.jpg
```

- **Miniatures** : JPEG, max 320×180, ratio conservé, qualité 60.
- **Nommage** : `YYYYMMDD_HHMMSS`.
- **latest/thumb_latest** : copie (pas symlink) pour compatibilité Windows.
- **Nettoyage** : automatique 24h après fermeture de session.

### Code groupe

- **Format** : 4 caractères alphanumériques majuscules.
- **Alphabet** : `ABCDEFGHJKMNPQRSTUVWXYZ23456789` (exclus : 0, O, 1, I, L).
- **Combinaisons** : 32⁴ = 1 048 576.
- **Unicité** : parmi les sessions actives.
- **Expiration** : 8 heures (configurable).

### Comportement perte de connexion

- Le client compte les échecs heartbeat consécutifs.
- Après `max_heartbeat_failures` (défaut: 3) échecs : `_emergency_shutdown()`.
- L'arrêt d'urgence restaure l'état proxy original avant de quitter.

### Comportement arrêt normal

- `quit()` appelle `restore_original()` systématiquement.
- Le proxy HKCU et Firefox sont remis dans leur état initial.
