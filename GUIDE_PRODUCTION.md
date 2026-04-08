# 🏫 Supervision — Guide de Déploiement et d'Utilisation en Production

## 📋 Table des matières
1. [Prérequis](#prérequis)
2. [Installation](#installation)
3. [Configuration](#configuration)
4. [Lancement](#lancement)
5. [Utilisation Professeur](#utilisation-professeur)
6. [Utilisation Élève](#utilisation-élève)
7. [Architecture Réseau](#architecture-réseau)
8. [Maintenance](#maintenance)
9. [Dépannage](#dépannage)

---

## 1. Prérequis

### Serveur
- **OS** : Linux (Ubuntu 22.04+, Debian 12+) recommandé
- **Docker** : version 24+ avec Docker Compose v2
- **RAM** : 2 Go minimum (4 Go recommandés pour 30+ élèves)
- **Disque** : 10 Go minimum (les captures d'écran occupent de l'espace)
- **Réseau** : IP fixe sur le réseau local de l'établissement
- **Port** : 3001 (TCP) ouvert sur le pare-feu

### Postes Élèves
- **OS** : Windows 10/11
- **Navigateur** : Chrome, Edge ou Firefox (pour télécharger le client)
- **Réseau** : Connecté au même réseau local que le serveur

### Poste Professeur
- **Navigateur** : Chrome, Edge ou Firefox (interface web)

---

## 2. Installation

### 2.1 Extraire l'archive
```bash
unzip supervision_server.zip -d /opt/supervision
cd /opt/supervision
```

### 2.2 Configurer les identifiants professeurs
Éditez le fichier `docker-compose.yml` :
```yaml
environment:
  - TEACHERS=prof1:MonMotDePasse,prof2:AutreMotDePasse
```

**Format** : `utilisateur:motdepasse` séparés par des virgules.

### 2.3 Générer les certificats SSL
Un certificat auto-signé est inclus. Pour le régénérer avec l'IP de votre serveur :
```bash
# Remplacez 192.168.1.100 par l'IP réelle de votre serveur
openssl req -x509 -newkey rsa:4096 -keyout server.key -out server.crt \
  -days 365 -nodes \
  -subj "/CN=Supervision" \
  -addext "subjectAltName=IP:192.168.1.100"
```

> ⚠️ **Important** : Le certificat inclus est générique. En production, regénérez-le avec l'IP exacte de votre serveur.

---

## 3. Configuration

### Fichier `docker-compose.yml`
```yaml
services:
  supervision-server:
    build: .
    container_name: supervision-server
    ports:
      - "3001:3001"          # Port d'écoute
    volumes:
      - ./uploads:/app/uploads   # Captures d'écran (persistant)
      - ./data:/app/data         # Sessions (persistant)
      - ./server.crt:/app/server.crt
      - ./server.key:/app/server.key
    environment:
      - TEACHERS=admin:password123   # ⚠️ À MODIFIER
    restart: unless-stopped
```

### Variables d'environnement

| Variable | Description | Exemple |
|----------|-------------|---------|
| `TEACHERS` | Comptes professeurs (user:pass,user2:pass2) | `dupont:SecurePass1` |
| `SECRET_KEY` | Clé de signature des cookies (auto-générée si absente) | `abcdef123456...` |

---

## 4. Lancement

### Démarrer le serveur
```bash
cd /opt/supervision
docker compose up -d --build
```

### Vérifier le statut
```bash
docker compose logs -f
```

### Arrêter le serveur
```bash
docker compose down
```

### Redémarrer
```bash
docker compose restart
```

---

## 5. Utilisation Professeur

### 5.1 Connexion
1. Ouvrir le navigateur sur : `https://<IP_SERVEUR>:3001`
2. Accepter l'avertissement de certificat (certificat auto-signé)
3. Se connecter avec ses identifiants

### 5.2 Créer une session
1. Cliquer sur **« Nouvelle session »**
2. Donner un nom (ex: « 3ème B - Mathématiques »)
3. Un **code à 4 lettres** est généré (ex: `ABCD`)
4. Communiquer ce code aux élèves (oral, tableau, projecteur)

### 5.3 Dashboard — Superviser les élèves
Une fois les élèves connectés, le dashboard affiche :
- **Vignettes en temps réel** de chaque écran d'élève
- **Statut** : en ligne (vert), inactif (orange), déconnecté (rouge)
- **Fenêtre active** de chaque poste

### 5.4 Actions disponibles

#### 🔒 Bloquer internet
1. Activer le toggle **« Bloquer internet »**
2. Choisir une **durée** : 5 min, 15 min, 30 min, 1 heure ou illimité
3. (Optionnel) Ajouter des **sites autorisés** dans la liste blanche
   - Un domaine par ligne : `wikipedia.org`, `education.gouv.fr`
   - Wildcards possibles : `*.edu.fr`
4. Cliquer sur **« 🚀 Activer le blocage »**
5. Le blocage se désactive automatiquement à la fin du timer

> 💡 Le serveur de supervision reste toujours accessible même pendant le blocage.

#### 💬 Envoyer un message
- Cliquer sur **« Message »**
- Choisir le type : info, avertissement, erreur
- Le message apparaît sur tous les écrans des élèves

#### 🌐 Ouvrir une URL
- Cliquer sur **« Ouvrir URL »**
- Entrer l'adresse (ex: `https://exercice.edu.fr`)
- La page s'ouvre automatiquement sur tous les postes élèves

#### 📸 Capturer tous
- Déclenche une capture d'écran immédiate de tous les postes

### 5.5 Consulter l'historique d'un élève
- Cliquer sur la vignette d'un élève
- Naviguer entre les 30 dernières captures avec ◀ / ▶

### 5.6 Fermer la session
- Cliquer sur **« Fermer la session »**
- Le blocage internet est automatiquement levé sur tous les postes
- Les clients élèves s'arrêtent proprement

---

## 6. Utilisation Élève

### 6.1 Rejoindre une session
1. Ouvrir le navigateur sur : `https://<IP_SERVEUR>:3001/join`
2. Accepter l'avertissement de certificat
3. Entrer le **code à 4 lettres** donné par le professeur
4. Télécharger le ZIP (bouton Windows)
5. Extraire le dossier `Supervision` sur le Bureau
6. Lancer `Supervision.exe`

### 6.2 Fonctionnement
- Le client se connecte **automatiquement** (le nom d'utilisateur Windows est détecté)
- Une icône apparaît dans la barre des tâches (zone de notification)
- Les captures d'écran sont envoyées toutes les 15 secondes
- **Le fichier de configuration est chiffré** et ne peut pas être modifié

### 6.3 Ce que voit l'élève
- Icône dans la barre des tâches indiquant le statut
- Messages du professeur (popups)
- Ouverture automatique d'URLs si demandé par le professeur

---

## 7. Architecture Réseau

```
┌─────────────────────────────────────────┐
│         Réseau Local Établissement       │
│                                          │
│  ┌──────────────┐    ┌──────────────┐   │
│  │  Serveur      │    │  Poste Prof  │   │
│  │  Docker       │◄───│  Navigateur  │   │
│  │  :3001 (HTTPS)│    │              │   │
│  └──────┬───────┘    └──────────────┘   │
│         │                                │
│    ┌────┼────┬────┬────┐                │
│    │    │    │    │    │                 │
│  ┌─┴─┐┌─┴─┐┌─┴─┐┌─┴─┐┌─┴─┐            │
│  │PC1││PC2││PC3││PC4││PC5│  Élèves     │
│  └───┘└───┘└───┘└───┘└───┘             │
└─────────────────────────────────────────┘
```

### Flux réseau
- **HTTPS (port 3001)** : Toutes les communications sont chiffrées
- **Heartbeat** : Chaque client envoie un signal toutes les 60 secondes
- **Captures** : Images PNG envoyées toutes les 15 secondes
- **SSE** : Le dashboard reçoit les mises à jour en temps réel

---

## 8. Maintenance

### Nettoyage des captures anciennes
Les captures sont stockées dans `./uploads/`. Pour nettoyer :
```bash
# Supprimer les captures de plus de 7 jours
find ./uploads -name "*.png" -mtime +7 -delete
find ./uploads -name "*.jpg" -mtime +7 -delete
```

### Mise à jour du serveur
```bash
docker compose down
# Remplacer les fichiers sources
docker compose up -d --build
```

### Sauvegarde
```bash
# Sauvegarder les données
tar -czf backup_supervision.tar.gz data/ uploads/
```

### Logs
```bash
# Voir les logs en direct
docker compose logs -f

# Voir les 100 dernières lignes
docker compose logs --tail 100
```

---

## 9. Dépannage

### Le client affiche "Offline"
- Vérifier que le serveur est accessible : `curl -k https://<IP>:3001`
- Vérifier que le port 3001 est ouvert dans le pare-feu
- Re-télécharger le ZIP depuis `/join` (le token a peut-être changé)

### Le certificat SSL est rejeté
- Régénérer le certificat avec l'IP correcte du serveur (voir section 2.3)
- Si `verify_ssl = false` dans le config.ini, le client ignore le certificat

### Le blocage internet ne fonctionne pas
- Vérifier que le client tourne **en tant qu'utilisateur standard** (pas admin)
- Certains navigateurs (Firefox) utilisent leur propre configuration proxy
- Le client gère automatiquement Chrome/Edge et Firefox

### L'élève n'apparaît pas sur le dashboard
- Vérifier les logs : `docker compose logs --tail 50`
- S'assurer que la session n'a pas expiré (8 heures par défaut)
- Le client doit envoyer au moins un heartbeat réussi

### Performances avec beaucoup d'élèves
- Réduire `capture_interval_s` à 30 secondes dans le config
- Augmenter la RAM du serveur à 4 Go+
- Utiliser un SSD pour le stockage des captures

---

## 📞 Support
En cas de problème, consulter les logs Docker et vérifier la connectivité réseau entre les postes et le serveur.
