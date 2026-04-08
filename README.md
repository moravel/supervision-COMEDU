# Supervision Server

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100.0-green)

Supervision Server est la composante serveur d'un écosystème de supervision pédagogique conçu pour les établissements scolaires. Il permet aux professeurs de créer des sessions sécurisées pour surveiller l'activité de postes informatiques clients (élèves), appliquer des restrictions d'accès à Internet et interagir en temps réel.

## ✨ Fonctionnalités Principales

- **Dashboard Temps Réel (SSE)** : Visualisation fluide des miniatures (captures d'écrans) des postes distants.
- **Blocage Internet Pédagogique** : Possibilité de désactiver la connexion internet globale d'un clic, tout en gardant certains sites vitaux sur liste blanche.
- **Communication** : Envoi de messages d'alertes, d'informations et ouverture à distance de pages web sur tous les postes de la session.
- **Communication Chiffrée** : Tous les échanges entre les clients distants et le serveur sont chiffrés et sécurisés via TLS (HTTPS) et un token (clé) de transport.
- **Distribution Automatique** : Les clients dédiés Windows se téléchargent et s'activent facilement à la volée.

## 🚀 Démarrage Rapide

### 1. Prérequis
- Python 3.9+ ou Docker
- OpenSSL (pour la génération des certificats SSL)

### 2. Générer les clés de sécurité
Pour interagir de façon chiffrée avec les clients distants et configurer HTTPS, générez vos certificats et tokens via :

```bash
python generate_security.py
```
> Ce script crée les fichiers nécessaires (`server.crt`, `server.key` et `transport.key`). Ils ont étés ignorés dans GIT pour rester confidentiels.

### 3. Installation et Déploiement

Deux méthodes principales de déploiement sont fournies dans ce dépôt :

- 👉 **[Guide de Production (Installation Standard)](./GUIDE_PRODUCTION.md)** : Documentation complète détaillant les usages professeurs, élèves et le fonctionnement général du logiciel.
- 👉 **[Déploiement Docker](./DOCKER_DEPLOYMENT.md)** : Guide technique rapide pour déployer ce serveur via un conteneur et docker-compose.

## 🔒 Confidentialité Prise en Charge
Le dépôt est configuré via son `.gitignore` pour ne publier ni vos clés de productions (`.key`, `.crt`, `.env`), ni vos historiques ou bases de données (`data/`, `uploads/`).

---
Développé avec 🛡️ pour l'éducation.
