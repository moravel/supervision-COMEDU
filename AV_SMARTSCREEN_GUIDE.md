# Guide : Alertes Windows SmartScreen et Antivirus

Ce document explique pourquoi Windows (via SmartScreen ou Windows Defender) peut afficher une alerte bloquante lorsqu'un élève tente d'exécuter `Supervision.exe`, et comment y remédier.

## 1. Pourquoi ces alertes apparaissent-elles ?

Le fait de voir un écran bleu *"Windows a protégé votre ordinateur"* ou une alerte antivirus lors du lancement du client n'est pas un bogue du projet, mais le comportement normal de sécurité de Windows. Cela s'explique par deux facteurs techniques :

1. **La "Mark of the Web" (MotW)** : Lorsque l'élève télécharge le fichier ZIP contenant le client depuis la page `/join` du serveur à l'aide de son navigateur, Windows marque ce fichier comme provenant d'Internet. Tout exécutable marqué de la sorte est considéré par défaut comme suspect sauf s'il prouve son intégrité.
2. **L'absence de Signature de Code (Authenticode) et PyInstaller** : Le fichier généré n'est pas signé numériquement par une *Autorité de Certification* publique. De plus, le client étant compilé avec **PyInstaller** (qui inclut un interpréteur Python embarqué), les moteurs heuristiques des antivirus ont tendance à faire des faux-positifs, car cette technologie est couramment utilisée par des logiciels malveillants.

---

## 2. Solutions et Remèdes

Plusieurs approches permettent d'éviter cette friction lors du déploiement en salle de classe.

### A. La Solution "Zéro Alerte" : Signature du code (Recommandé)
Pour que Windows fasse immédiatement confiance à l'application sans lancer d'alerte, l'exécutable doit être signé.
* **Marche à suivre** : Rapprochez-vous du service informatique (DSI) pour utiliser un certificat de signature de code commercial (EV ou OV Validation) au nom du lycée/établissement, ou générez un certificat depuis votre PKI d'entreprise.
* Signez le binaire `Supervision.exe` avant de le placer dans le dossier `client_binaries/` du serveur.

### B. La Solution "Sans Téléchargement" : Préinstallation
Si The Mark of the Web est le problème, la solution est de ne pas faire télécharger le programme via un navigateur par l'élève.
* **Marche à suivre** : Le service informatique peut déployer massivement le dossier `Supervision` sur les disques des machines élèves (`C:\Program Files\Supervision\` par exemple) en utilisant des outils de gestion de parc (GPO, MDM, Intune, OCS Inventory).
* L'élève n'aura plus qu'à double-cliquer sur le raccourci mis à sa disposition sur le Bureau. Sans étiquette "téléchargé depuis le Web", la friction SmartScreen est contournée.

### C. La Solution "Stratégie de Groupe" (Whitelist GPO)
Si vous conservez le téléchargement depuis la page `/join` mais que vous administrez le réseau de l'école (Active Directory) :
* **Marche à suivre** : Déployez une règle par GPO aux machines du domaine pour ajouter une exclusion (Whitelist) dans Windows Defender sur le hash du fichier `Supervision.exe`, ou sur le dossier de téléchargement spécifique, ou bien signez le code avec une PKI d'entreprise approuvée par les GPO.

### D. Contournement manuel (Pour tests uniquement)
Cette solution offre la pire expérience utilisateur mais fonctionne lors d'essais ponctuels :
Lors de l'apparition de l'écran bleu SmartScreen, demandez aux élèves de cliquer sur le texte discret **"Informations complémentaires"** puis sur le bouton **"Exécuter quand même"**.
