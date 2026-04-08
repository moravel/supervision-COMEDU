# Guide de Déploiement Docker — Supervision Server

Ce guide explique comment déployer le serveur de supervision en utilisant Docker et Docker Compose.

## 📋 Prérequis
- Docker installé sur la machine hôte.
- Docker Compose (souvent inclus avec Docker Desktop).

## 🚀 Lancement Rapide

1.  **Extraire l'archive** `server_docker.zip`.
2.  **Générer les certificats SSL** (Optionnel mais recommandé) :
    Si vous n'avez pas encore de certificats, lancez le script python (nécessite `openssl` installé) :
    ```bash
    python generate_security.py
    ```
    Cela créera `server.crt`, `server.key` et `transport.key`.
3.  **Démarrer le serveur** :
    ```bash
    docker-compose up -d --build
    ```
4.  **Accéder au dashboard** :
    Rendez-vous sur `https://localhost:3001` (ou `http` si SSL n'est pas configuré).

## 📁 Structure des Fichiers

```text
.
├── docker-compose.yml   # Configuration du service
├── Dockerfile           # Recette de l'image
├── app.py               # Code principal FastAPI
├── requirements.txt     # Dépendances Python
├── client_binaries/     # Doit contenir Supervision.exe
├── data/                # Dossier persistant (sessions)
└── uploads/             # Dossier persistant (captures)
```

## 🔐 Sécurité

- **SSL** : Si `server.crt` et `server.key` sont présents à la racine du dossier lors du `docker-compose up`, le serveur démarrera automatiquement en mode HTTPS.
- **Identifiants Professeur** : Vous pouvez changer les identifiants par défaut en éditant la variable `TEACHERS` dans le fichier `docker-compose.yml`.
- **Clé Secrète** : Modifiez `SECRET_KEY` pour sécuriser les cookies de session.

## 🛠️ Maintenance

- **Voir les logs** : `docker-compose logs -f`
- **Arrêter le serveur** : `docker-compose down`
- **Mettre à jour** : Copiez les nouveaux fichiers et relancez `docker-compose up -d --build`.
