import os
import zipfile

def package_server(output_filename="server_docker.zip"):
    # Fichiers et dossiers à inclure
    include_patterns = [
        "app.py", "auth.py", "cleanup.py", "download.py", "models.py",
        "sessions.py", "sse.py", "thumbnail.py", "requirements.txt",
        "Dockerfile", "docker-compose.yml", "DOCKER_DEPLOYMENT.md",
        "generate_security.py",
        "templates/", "static/", "client_binaries/", "data/", "uploads/"
    ]
    
    # Dossiers à ignorer
    ignore_patterns = ["venv", "__pycache__", ".git", ".pytest_cache"]

    with zipfile.ZipFile(output_filename, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk("."):
            # Filtrer les dossiers ignorés
            dirs[:] = [d for d in dirs if d not in ignore_patterns]
            
            for file in files:
                rel_path = os.path.relpath(os.path.join(root, file), ".")
                
                # Vérifier si le fichier ou son dossier parent est dans les includes
                should_include = False
                for pattern in include_patterns:
                    if pattern.endswith("/"):
                        if rel_path.startswith(pattern):
                            should_include = True
                            break
                    elif rel_path == pattern:
                        should_include = True
                        break
                
                if should_include:
                    print(f"Adding {rel_path}...")
                    zf.write(rel_path)

    print(f"\n✅ Packaged into {output_filename}")

if __name__ == "__main__":
    package_server()
