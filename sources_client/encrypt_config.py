#!/usr/bin/env python3
"""
encrypt_config.py — Script autonome pour chiffrer les valeurs sensibles du config.ini.

Usage (en tant qu'administrateur sur le poste cible) :
    python encrypt_config.py --config config.ini --fields auth_token,server_url

Ce script :
1. Lit le SID Windows de l'utilisateur courant.
2. Dérive une clé Fernet à partir du SID.
3. Chiffre les champs spécifiés et les préfixe avec "ENC:".
4. Sauvegarde le fichier config.ini modifié.

La clé étant dérivée du SID, le fichier ne peut être déchiffré que
sur le même poste, par le même utilisateur Windows.
"""

import argparse
import base64
import configparser
import hashlib
import os
import platform
import sys

try:
    from cryptography.fernet import Fernet
except ImportError:
    print("ERROR: 'cryptography' package required. Install with: pip install cryptography")
    sys.exit(1)


def get_windows_sid() -> str:
    """Récupère le SID Windows de l'utilisateur courant."""
    if platform.system() != "Windows":
        print("WARNING: Not on Windows. Using fallback SID (for dev/testing only).")
        return os.environ.get("USER", "fallback-sid")

    import subprocess
    result = subprocess.run(
        ["whoami", "/user"],
        capture_output=True, text=True, timeout=5,
    )
    if result.returncode != 0:
        print(f"ERROR: whoami failed: {result.stderr}")
        sys.exit(1)

    sid = result.stdout.strip().split()[-1]
    print(f"SID detected: {sid}")
    return sid


def derive_key(sid: str) -> bytes:
    """Dérive une clé Fernet à partir du SID."""
    return base64.urlsafe_b64encode(hashlib.sha256(sid.encode()).digest())


def encrypt_value(fernet: Fernet, value: str) -> str:
    """Chiffre une valeur et retourne avec préfixe ENC:."""
    if value.startswith("ENC:"):
        print(f"  → Already encrypted, skipping.")
        return value
    encrypted = fernet.encrypt(value.encode()).decode()
    return f"ENC:{encrypted}"


def decrypt_value(fernet: Fernet, value: str) -> str:
    """Déchiffre une valeur préfixée ENC: (pour vérification)."""
    if not value.startswith("ENC:"):
        return value
    encrypted = value[4:]
    return fernet.decrypt(encrypted.encode()).decode()


def main():
    parser = argparse.ArgumentParser(
        description="Chiffrer les valeurs sensibles du config.ini",
    )
    parser.add_argument(
        "--config", default="config.ini",
        help="Chemin vers le fichier config.ini",
    )
    parser.add_argument(
        "--fields", default="auth_token,server_url",
        help="Champs à chiffrer (séparés par des virgules)",
    )
    parser.add_argument(
        "--decrypt", action="store_true",
        help="Mode déchiffrement (affiche les valeurs déchiffrées)",
    )
    parser.add_argument(
        "--verify", action="store_true",
        help="Vérifier que les valeurs chiffrées sont déchiffrables",
    )
    args = parser.parse_args()

    config_path = args.config
    if not os.path.exists(config_path):
        print(f"ERROR: Config file not found: {config_path}")
        sys.exit(1)

    # Obtenir la clé
    sid = get_windows_sid()
    key = derive_key(sid)
    fernet = Fernet(key)

    # Lire le config
    config = configparser.ConfigParser()
    config.read(config_path, encoding='utf-8')

    fields = [f.strip() for f in args.fields.split(",")]

    if args.verify or args.decrypt:
        # Mode vérification/déchiffrement
        print(f"\n{'Decrypting' if args.decrypt else 'Verifying'} fields in {config_path}:")
        for field in fields:
            if 'Settings' in config and field in config['Settings']:
                value = config['Settings'][field]
                if value.startswith("ENC:"):
                    try:
                        decrypted = decrypt_value(fernet, value)
                        print(f"  {field}: ✅ {decrypted if args.decrypt else '[OK]'}")
                    except Exception as e:
                        print(f"  {field}: ❌ Decryption failed: {e}")
                else:
                    print(f"  {field}: ⚠ Not encrypted (plaintext)")
            else:
                print(f"  {field}: ⚠ Not found in config")
        return

    # Mode chiffrement
    print(f"\nEncrypting fields in {config_path}:")
    modified = False

    for field in fields:
        if 'Settings' not in config:
            config['Settings'] = {}

        if field in config['Settings']:
            value = config['Settings'][field]
            if not value:
                print(f"  {field}: ⚠ Empty value, skipping")
                continue
            print(f"  {field}: '{value[:20]}{'...' if len(value) > 20 else ''}'")
            encrypted = encrypt_value(fernet, value)
            config['Settings'][field] = encrypted
            modified = True
            print(f"         → encrypted ✅")
        else:
            print(f"  {field}: ⚠ Not found in [Settings]")

    if modified:
        # Sauvegarder
        with open(config_path, 'w', encoding='utf-8') as f:
            config.write(f)
        print(f"\n✅ Config saved to {config_path}")
        print("⚠  IMPORTANT: This file is now tied to this user's SID on this machine.")
    else:
        print("\nNo changes made.")


if __name__ == "__main__":
    main()
