"""
app.py — Application FastAPI pour le serveur de supervision scolaire.
Tous les endpoints : heartbeat, upload, sessions, dashboard, SSE, media.
"""

import asyncio
import os
import shutil
import logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, Form, UploadFile, File, Depends
from fastapi.responses import (
    HTMLResponse, JSONResponse, RedirectResponse,
    FileResponse, StreamingResponse, Response,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from models import Session, ClientInfo
from sessions import SessionManager
from thumbnail import generate_thumbnail
from sse import SSEManager
from auth import (
    require_teacher, require_client_token, get_teacher_from_request,
    authenticate_teacher, create_session_cookie, COOKIE_NAME,
)
from cleanup import cleanup_expired_sessions, cleanup_session_files
from download import create_windows_package, check_client_available
from auth import CLIENT_AUTH_TOKEN

# ── Configuration ────────────────────────────────────────────────

UPLOADS_DIR = os.environ.get("UPLOADS_DIR", "uploads")
STATUS_UPDATE_INTERVAL = 10  # secondes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("supervision-server")

# ── Instances globales ───────────────────────────────────────────

session_manager = SessionManager()
sse_manager = SSEManager()


# ── Background tasks ─────────────────────────────────────────────

async def status_update_loop():
    """Envoie un status_update SSE toutes les 10 secondes pour chaque session active."""
    while True:
        await asyncio.sleep(STATUS_UPDATE_INTERVAL)
        for code, session in list(session_manager.sessions.items()):
            if not session.is_active:
                continue
            clients_status = [
                {
                    "login": c.login,
                    "status": c.status,
                    "last_seen": c.last_seen.isoformat(),
                    "active_window": c.active_window,
                }
                for c in session.clients.values()
            ]
            await sse_manager.broadcast_status_update(code, clients_status)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup et shutdown de l'application."""
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    os.makedirs("data", exist_ok=True)

    # Lancer les tâches de fond
    cleanup_task = asyncio.create_task(cleanup_expired_sessions(session_manager))
    status_task = asyncio.create_task(status_update_loop())

    logger.info("Supervision server started.")
    yield

    cleanup_task.cancel()
    status_task.cancel()
    logger.info("Supervision server stopped.")


# ── Application FastAPI ──────────────────────────────────────────

app = FastAPI(title="Supervision Scolaire", lifespan=lifespan)

# Fichiers statiques et templates
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ══════════════════════════════════════════════════════════════════
# ENDPOINTS PROFESSEUR — Interface Web
# ══════════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Redirige vers la page de connexion ou les sessions."""
    teacher = get_teacher_from_request(request)
    if teacher:
        return RedirectResponse("/sessions", status_code=302)
    return RedirectResponse("/login", status_code=302)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", context={"error": None})


@app.post("/login")
async def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    if not authenticate_teacher(username, password):
        return templates.TemplateResponse(
            request,
            "login.html",
            context={"error": "Identifiants invalides"},
            status_code=401,
        )
    response = RedirectResponse("/sessions", status_code=302)
    cookie_value = create_session_cookie(username)
    response.set_cookie(COOKIE_NAME, cookie_value, max_age=8 * 3600, httponly=True, samesite="lax")
    return response


@app.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response


@app.get("/sessions", response_class=HTMLResponse)
async def sessions_page(request: Request):
    teacher_id = require_teacher(request)
    sessions = session_manager.get_teacher_sessions(teacher_id)
    # Trier : actives d'abord, puis par date de création décroissante
    sessions.sort(key=lambda s: (not s.is_active, s.created_at), reverse=False)
    active_first = sorted(sessions, key=lambda s: (not s.is_active, -s.created_at.timestamp()))
    return templates.TemplateResponse(request, "sessions.html", context={
        "teacher_id": teacher_id,
        "sessions": active_first,
    })


@app.get("/dashboard/{group_code}", response_class=HTMLResponse)
async def dashboard_page(request: Request, group_code: str):
    teacher_id = require_teacher(request)
    session = session_manager.get_active_session(group_code)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or inactive")
    if session.teacher_id != teacher_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return templates.TemplateResponse(request, "dashboard.html", context={
        "session": session,
        "teacher_id": teacher_id,
    })


# ══════════════════════════════════════════════════════════════════
# ENDPOINTS API — Gestion de sessions (Tâche 3)
# ══════════════════════════════════════════════════════════════════

@app.post("/session/create")
async def session_create(request: Request):
    teacher_id = require_teacher(request)
    body = await request.json()
    label = body.get("label", "")
    expires_in_hours = body.get("expires_in_hours", 8)

    session = session_manager.create_session(teacher_id, label, expires_in_hours)
    return JSONResponse({
        "group_code": session.group_code,
        "session_id": session.id,
        "expires_at": session.expires_at.isoformat(),
    })


@app.post("/session/close")
async def session_close(request: Request):
    teacher_id = require_teacher(request)
    body = await request.json()
    group_code = body.get("group_code", "")

    session = session_manager.get_session(group_code)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.teacher_id != teacher_id:
        raise HTTPException(status_code=403, detail="Access denied")

    session_manager.close_session(group_code)
    sse_manager.close_session_streams(group_code)

    # Planifier le nettoyage dans 24h
    asyncio.create_task(cleanup_session_files(group_code))

    return JSONResponse({"success": True})


@app.get("/session/{group_code}/clients")
async def session_clients(request: Request, group_code: str):
    teacher_id = require_teacher(request)
    session = session_manager.get_active_session(group_code)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.teacher_id != teacher_id:
        raise HTTPException(status_code=403, detail="Access denied")

    clients = [c.to_dict() for c in session.clients.values()]
    return JSONResponse(clients)


@app.get("/session/{group_code}/directives")
async def session_get_directives(request: Request, group_code: str):
    teacher_id = require_teacher(request)
    session = session_manager.get_active_session(group_code)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.teacher_id != teacher_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return JSONResponse(session.directives)


@app.put("/session/{group_code}/directives")
async def session_update_directives(request: Request, group_code: str):
    teacher_id = require_teacher(request)
    session = session_manager.get_active_session(group_code)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.teacher_id != teacher_id:
        raise HTTPException(status_code=403, detail="Access denied")

    body = await request.json()
    session_manager.update_directives(group_code, body)
    return JSONResponse({"success": True})


# ══════════════════════════════════════════════════════════════════
# ENDPOINTS — Thumbnails & Dashboard (Tâche 2)
# ══════════════════════════════════════════════════════════════════

@app.get("/session/{group_code}/thumbnails")
async def session_thumbnails(request: Request, group_code: str):
    teacher_id = require_teacher(request)
    session = session_manager.get_active_session(group_code)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.teacher_id != teacher_id:
        raise HTTPException(status_code=403, detail="Access denied")

    result = []
    for client in session.clients.values():
        thumb_path = os.path.join(UPLOADS_DIR, group_code, client.login, "thumb_latest.jpg")
        original_path = os.path.join(UPLOADS_DIR, group_code, client.login, "latest.png")

        has_thumb = os.path.exists(thumb_path)
        result.append({
            "login": client.login,
            "status": client.status,
            "active_window": client.active_window,
            "last_seen": client.last_seen.isoformat(),
            "last_thumb_at": client.last_thumb_at.isoformat() if client.last_thumb_at else None,
            "thumbnail_url": f"/media/{group_code}/{client.login}/thumb_latest.jpg" if has_thumb else None,
            "original_url": f"/media/{group_code}/{client.login}/latest.png" if os.path.exists(original_path) else None,
            "captured_at": client.last_thumb_at.isoformat() if client.last_thumb_at else None,
        })

    return JSONResponse(result)


@app.get("/session/{group_code}/stream")
async def session_stream(request: Request, group_code: str):
    """Endpoint SSE — flux temps réel pour le dashboard."""
    teacher_id = require_teacher(request)
    session = session_manager.get_active_session(group_code)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.teacher_id != teacher_id:
        raise HTTPException(status_code=403, detail="Access denied")

    async def event_generator():
        async for event in sse_manager.subscribe(group_code):
            yield event

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/session/{group_code}/client/{login}/capture")
async def trigger_capture(request: Request, group_code: str, login: str):
    """Déclenche une capture immédiate sur un client spécifique."""
    teacher_id = require_teacher(request)
    session = session_manager.get_active_session(group_code)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.teacher_id != teacher_id:
        raise HTTPException(status_code=403, detail="Access denied")
    if login not in session.clients:
        raise HTTPException(status_code=404, detail="Client not found")

    session_manager.set_capture_now(group_code, login)
    return JSONResponse({"success": True})


# ══════════════════════════════════════════════════════════════════
# ENDPOINTS — Media (Tâche 2.3, 2.4, 2.5)
# ══════════════════════════════════════════════════════════════════

@app.get("/media/{group_code}/{login}/thumb_latest.jpg")
async def media_thumb_latest(request: Request, group_code: str, login: str):
    require_teacher(request)
    file_path = os.path.join(UPLOADS_DIR, group_code, login, "thumb_latest.jpg")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    return FileResponse(
        file_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-cache, no-store"},
    )


@app.get("/media/{group_code}/{login}/latest.png")
async def media_latest(request: Request, group_code: str, login: str):
    require_teacher(request)
    file_path = os.path.join(UPLOADS_DIR, group_code, login, "latest.png")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return FileResponse(
        file_path,
        media_type="image/png",
        headers={"Cache-Control": "no-cache, no-store"},
    )


@app.get("/media/{group_code}/{login}/history")
async def media_history(request: Request, group_code: str, login: str):
    require_teacher(request)
    history_dir = os.path.join(UPLOADS_DIR, group_code, login, "history")
    if not os.path.exists(history_dir):
        return JSONResponse([])

    entries = []
    for filename in sorted(os.listdir(history_dir), reverse=True):
        if filename.endswith(".png") and not filename.endswith("_thumb.jpg"):
            timestamp = filename.rsplit(".", 1)[0]  # ex: 20260403_093214
            thumb_filename = f"{timestamp}_thumb.jpg"

            # Parse timestamp pour captured_at
            try:
                captured_dt = datetime.strptime(timestamp, "%Y%m%d_%H%M%S")
                captured_at = captured_dt.isoformat()
            except ValueError:
                captured_at = None

            entries.append({
                "timestamp": timestamp,
                "original_url": f"/media/{group_code}/{login}/history/{filename}",
                "thumbnail_url": f"/media/{group_code}/{login}/history/{thumb_filename}",
                "captured_at": captured_at,
            })
            if len(entries) >= 30:
                break

    return JSONResponse(entries)


@app.get("/media/{group_code}/{login}/history/{filename}")
async def media_history_file(request: Request, group_code: str, login: str, filename: str):
    require_teacher(request)
    file_path = os.path.join(UPLOADS_DIR, group_code, login, "history", filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    media_type = "image/jpeg" if filename.endswith(".jpg") else "image/png"
    return FileResponse(
        file_path,
        media_type=media_type,
        headers={"Cache-Control": "no-cache, no-store"},
    )


# ══════════════════════════════════════════════════════════════════
# ENDPOINTS CLIENT — Heartbeat & Upload (Tâches 1, 3.6)
# ══════════════════════════════════════════════════════════════════

async def _process_screenshot(group_code: str, login: str, screenshot: UploadFile):
    """
    Traite un screenshot uploadé : sauvegarde, miniature, copie latest.
    Retourne le timestamp de capture.
    """
    base_dir = os.path.join(UPLOADS_DIR, group_code, login)
    history_dir = os.path.join(base_dir, "history")
    os.makedirs(history_dir, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    original_path = os.path.join(history_dir, f"{ts}.png")
    thumb_path = os.path.join(history_dir, f"{ts}_thumb.jpg")
    latest_path = os.path.join(base_dir, "latest.png")
    thumb_latest = os.path.join(base_dir, "thumb_latest.jpg")

    # 1. Sauvegarder le fichier
    content = await screenshot.read()
    with open(original_path, "wb") as f:
        f.write(content)

    # 2. Générer la miniature (opération bloquante via executor)
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, generate_thumbnail, original_path, thumb_path)

    # 3. Copier vers latest (pas symlink pour compatibilité Windows)
    shutil.copy2(original_path, latest_path)
    if os.path.exists(thumb_path):
        shutil.copy2(thumb_path, thumb_latest)

    return ts


@app.post("/heartbeat")
async def heartbeat(
    request: Request,
    login: str = Form(...),
    group_code: str = Form(...),
    timestamp: str = Form(None),
    active_window: str = Form(None),
    screenshot: UploadFile = File(None),
):
    """
    Endpoint heartbeat principal.
    Reçoit les infos du client, retourne les directives de la session.
    """
    # 1. Valider group_code et obtenir la session
    group_code = group_code.upper()
    session = session_manager.get_session(group_code)

    if not session:
        raise HTTPException(status_code=404, detail="Group code not found")

    # 2. Vérifier token spécifique à la session
    require_client_token(request, expected_token=session.auth_token)

    if not session.is_active:
        raise HTTPException(status_code=410, detail="Session closed")

    # 3. Enregistrer/valider le client
    ip = request.client.host if request.client else ""
    client, error = session_manager.register_client(group_code, login, ip)

    if error == "not_found":
        raise HTTPException(status_code=404, detail="Group code not found")
    elif error == "session_closed":
        raise HTTPException(status_code=410, detail="Session closed")
    elif error == "login_already_bound":
        raise HTTPException(status_code=409, detail="login_already_bound")

    # 4. Mettre à jour le client
    now = datetime.now(timezone.utc)
    session_manager.update_client(
        group_code, login,
        active_window=active_window or "",
        ip_address=ip,
    )

    # 5. Traiter screenshot si présent
    captured_at = None
    if screenshot and screenshot.filename:
        try:
            ts = await _process_screenshot(group_code, login, screenshot)
            session_manager.update_client(group_code, login, last_thumb_at=now)
            captured_at = now.isoformat()
        except Exception as e:
            logger.error(f"Error processing screenshot for {login}: {e}")

    # 6. Notifier le flux SSE (signale la présence même sans image)
    client_obj = session.clients.get(login)
    if client_obj:
        await sse_manager.broadcast(group_code, {
            "type": "new_thumbnail",
            "login": login,
            "status": client_obj.status,
            "active_window": active_window or "",
            "last_seen": now.isoformat(),
            "captured_at": captured_at,
        })
        logger.info(f"Heartbeat success for {login} in {group_code}")
    
    # 7. Retourner les directives
    directives = session_manager.get_client_directives(group_code, login)
    return JSONResponse(directives or {})


@app.post("/upload-screenshot")
async def upload_screenshot(
    request: Request,
    login: str = Form(...),
    group_code: str = Form(...),
    timestamp: str = Form(None),
    screenshot: UploadFile = File(...),
):
    """
    Endpoint d'upload de screenshot dédié.
    """
    # 1. Valider session et obtenir le token
    group_code = group_code.upper()
    session = session_manager.get_active_session(group_code)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or inactive")

    # 2. Vérifier token spécifique à la session
    require_client_token(request, expected_token=session.auth_token)
    if login not in session.clients:
        raise HTTPException(status_code=404, detail="Client not registered. Send heartbeat first.")

    # 3. Traiter le screenshot
    now = datetime.now(timezone.utc)
    ts = await _process_screenshot(group_code, login, screenshot)

    # 4. Mettre à jour
    session_manager.update_client(group_code, login, last_thumb_at=now)

    # 5. Notifier SSE
    client = session.clients.get(login)
    await sse_manager.broadcast(group_code, {
        "type": "new_thumbnail",
        "login": login,
        "status": client.status if client else "active",
        "active_window": client.active_window if client else "",
        "last_seen": now.isoformat(),
        "last_thumb_at": now.isoformat(),
        "thumbnail_url": f"/media/{group_code}/{login}/thumb_latest.jpg",
        "original_url": f"/media/{group_code}/{login}/latest.png",
        "captured_at": now.isoformat(),
    })

    return JSONResponse({"success": True})


# ══════════════════════════════════════════════════════════════════
# ENDPOINTS PUBLICS — Téléchargement Client (Page /join)
# ══════════════════════════════════════════════════════════════════

@app.get("/join", response_class=HTMLResponse)
async def join_page(request: Request):
    """Page publique pour les élèves — saisie du code session."""
    return templates.TemplateResponse(request, "join.html")


@app.post("/join/validate")
async def join_validate(request: Request):
    """
    Valide un code de session (public, pas d'auth requise).
    Retourne les infos de base de la session si elle est active.
    """
    body = await request.json()
    group_code = body.get("group_code", "").strip().upper()

    if not group_code or len(group_code) != 4:
        raise HTTPException(status_code=400, detail="Code de session invalide")

    session = session_manager.get_active_session(group_code)
    if not session:
        raise HTTPException(status_code=404, detail="Code de session invalide ou session expirée")

    return JSONResponse({
        "valid": True,
        "group_code": session.group_code,
        "label": session.label,
        "teacher_id": session.teacher_id,
    })


@app.get("/join/download/{group_code}/{platform}")
async def join_download(request: Request, group_code: str, platform: str):
    """
    Télécharge le client pré-configuré pour une session.
    Génère un ZIP contenant l'exe + config.ini avec les bons paramètres.
    """
    group_code = group_code.strip().upper()
    platform = platform.strip().lower()

    # Valider session
    session = session_manager.get_active_session(group_code)
    if not session:
        raise HTTPException(status_code=404, detail="Session invalide ou expirée")

    if platform != "windows":
        raise HTTPException(status_code=400, detail="Plateforme non supportée. Utilisez 'windows'.")

    # Déterminer l'URL du serveur depuis la requête
    host = request.headers.get("host", "localhost:3001")
    scheme = request.url.scheme
    if "x-forwarded-proto" in request.headers:
        scheme = request.headers["x-forwarded-proto"]
    if "x-forwarded-host" in request.headers:
        host = request.headers["x-forwarded-host"]
    server_url = f"{scheme}://{host}"

    try:
        zip_buffer = create_windows_package(
            server_url=server_url,
            auth_token=session.auth_token,
            group_code=group_code,
            session_id=session.id
        )
    except FileNotFoundError as e:
        logger.error(f"Client binary not found: {e}")
        raise HTTPException(status_code=500, detail="Client non disponible sur le serveur")

    filename = f"Supervision_{group_code}.zip"
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


# ══════════════════════════════════════════════════════════════════
# Point d'entrée
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 3001))
    
    # SSL Configuration if certs exist
    ssl_cert = "server.crt"
    ssl_key = "server.key"
    ssl_args = {}
    if os.path.exists(ssl_cert) and os.path.exists(ssl_key):
        logger.info(f"Starting server with SSL support (HTTPS)")
        ssl_args = {
            "ssl_certfile": ssl_cert,
            "ssl_keyfile": ssl_key
        }
    else:
        logger.warning("SSL certificates not found. Starting in HTTP mode.")

    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True, **ssl_args)
