import os
import subprocess
import base64
import hashlib

def generate_certs():
    """
    Génère un jeu de certificats SSL auto-signés (server.crt et server.key)
    pour activer le support HTTPS sur le serveur FastAPI.
    """
    cert_file = "server.crt"
    key_file = "server.key"
    
    # Éviter de remplacer les certificats s'ils ont déjà été générés
    if os.path.exists(cert_file) and os.path.exists(key_file):
        print("Certificats SSL déjà présents.")
        return

    print("Génération des certificats SSL auto-signés...")
    # Appel système à la commande 'openssl' pour générer une clé RSA 4096 bits.
    # Valide pendant 365 jours. Le paramètre -nodes permet de ne pas chiffrer 
    # la clé privée avec un mot de passe (pour que FastAPI puisse démarrer tout seul).
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:4096", "-keyout", key_file,
        "-out", cert_file, "-days", "365", "-nodes",
        "-subj", "/CN=SupervisionServer"
    ], check=True)
    print(f"Fichiers générés avec succès : {cert_file} et {key_file}.")


def generate_transport_key():
    """
    Génère la clé de transport secrète (transport.key). 
    Cette clé est utilisée pour chiffrer le fichier de configuration (config.ini)
    qui est envoyé dans l'archive .zip aux élèves. Cela empêche les élèves
    de lire en clair l'URL du serveur ou les tokens.
    """
    key_file = "transport.key"
    if os.path.exists(key_file):
        print("Clé de transport déjà présente.")
        return
        
    # Génération d'une clé Fernet de base.
    # Note: En production critique, ce 'secret' devrait être aléatoire cryptographiquement.
    secret = b"supervision-agent-transport-secret-2026"
    # Création du hash SHA-256 encodé en base64 pour être compatible avec les clés Fernet.
    key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest()).decode()
    
    with open(key_file, "w") as f:
        f.write(key)
    print(f"Fichier généré avec succès : {key_file}.")


if __name__ == "__main__":
    # Création du dossier data s'il n'existe pas, où seront stockées les 
    # informations persistantes (bases de données locales, sessions, etc.).
    os.makedirs("data", exist_ok=True)
    
    # Empaqueter et configurer tous les secrets.
    generate_certs()
    generate_transport_key()

