# Contribuer au projet Supervision-COMEDU

Tout d'abord, merci de l'intérêt que vous portez à ce projet scolaire de supervision ! Que ce soit pour signaler un bug, proposer une fonctionnalité ou corriger du code, toutes les contributions sont les bienvenues.

Ce document détaille les bonnes pratiques à suivre pour faciliter la collaboration.

---

## 🐞 1. Signaler un Bug ou Proposer une Idée
Avant de commencer à coder de votre côté, commencez toujours par ouvrir une **Issue** sur GitHub.
- **Pour un bug** : décrivez le comportement attendu, le comportement actuel, et les étapes pour le reproduire.
- **Pour une idée** : expliquez le besoin (côté professeur ou côté élève) et proposez votre solution.

---

## 🛠️ 2. Installer l'environnement de développement

Si vous souhaitez modifier le code, vous aurez besoin de configurer l'environnement local :

1. **Cloner le dépôt** :
   ```bash
   git clone https://github.com/moravel/supervision-COMEDU.git
   cd supervision-COMEDU
   ```

2. **Créer un environnement virtuel Python** (recommandé) :
   ```bash
   python -m venv venv
   source venv/bin/activate  # Sur Windows: venv\Scripts\activate
   ```

3. **Installer les dépendances** :
   ```bash
   pip install -r requirements.txt
   ```

4. **Générer les clés de sécurité pour le développement** :
   Le fonctionnement du serveur nécessite des clés pour initier la communication sécurisée. Lancez le script prévu à cet effet (il est ignoré par le contrôle de version pour garantir la sécurité) :
   ```bash
   python generate_security.py
   ```

---

## 🔄 3. Le Processus de Contribution (GitHub Flow)

La branche `master` de ce dépôt contient toujours un code de production **fiable et déployable**.

Pour proposer vos modifications, suivez ces étapes :

### Étape A : Créer une branche
Ne travaillez jamais directement sur `master`. Créez toujours une branche descriptive.
```bash
git checkout master
git pull
git checkout -b ajout-nouvelle-fonctionnalite
```

### Étape B : Faire vos commits
Faites des commits clairs et "atomiques" (un commit = un petit changement logique).
Exemples de bons messages de commit :
- `feat: ajout du bouton pour bannir l'accès USB`
- `fix: correction de la déconnexion inopinée au démarrage`
- `docs: mise à jour des notes d'installation`

### Étape C : Pousser et ouvrir une Pull Request
1. Poussez votre branche sur votre fork ou sur le dépôt (si vous y avez accès) :
   ```bash
   git push origin ajout-nouvelle-fonctionnalite
   ```
2. Rendez-vous sur GitHub et ouvrez une **Pull Request** (PR) vers la branche `master`.
3. Décrivez clairement ce que fait la PR (liez l'Issue d'origine si elle existe : "Fixes #12").

### Étape D : Revue de Code
L'administrateur ou d'autres contributeurs reliront votre code. Des modifications peuvent vous être demandées. Une fois la PR validée, elle sera "mergée" dans la branche principale !

---

## 📏 4. Règles de codage

*   **Langage** : Python 3.9+ 
*   **Architecture** : FastAPI
*   **Style** : Essayez de respecter la structure existante et utilisez des noms de variables explicites, idéalement en anglais ou français standardisé, en fonction des conventions actuelles du projet. 
*   **Confidentialité** : N'ajoutez **jamais** de fichiers contenant des informations sensibles (`.env`, certificats, listes d'élèves).

Encore merci de votre aide pour faire grandir ce projet !
