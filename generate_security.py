import os
import subprocess
import base64
import hashlib

def generate_certs():
    cert_file = "server.crt"
    key_file = "server.key"
    
    if os.path.exists(cert_file) and os.path.exists(key_file):
        print("Certificates already exist.")
        return

    print("Generating self-signed SSL certificates...")
    # Generate self-signed certificate (valid for 1 year)
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:4096", "-keyout", key_file,
        "-out", cert_file, "-days", "365", "-nodes",
        "-subj", "/CN=SupervisionServer"
    ], check=True)
    print(f"Generated {cert_file} and {key_file}.")

def generate_transport_key():
    key_file = "transport.key"
    if os.path.exists(key_file):
        print("Transport key already exists.")
        return
        
    # Generate a Fernet key
    # In a real app, this should be secret. For this project, we'll use a derived one.
    secret = b"supervision-agent-transport-secret-2026"
    key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest()).decode()
    
    with open(key_file, "w") as f:
        f.write(key)
    print(f"Generated {key_file}.")

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    # Put them in server/data or root? 
    # Let's put them in server/ for now.
    generate_certs()
    generate_transport_key()
