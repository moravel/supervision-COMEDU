"""
cleanup.py — Nettoyage planifié des fichiers de session expirées.
"""

import asyncio
import os
import shutil
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

UPLOADS_DIR = "uploads"


async def cleanup_expired_sessions(session_manager, interval_minutes: int = 60):
    """
    Tâche de fond qui nettoie les fichiers des sessions 
    fermées depuis plus de 24 heures.
    S'exécute toutes les `interval_minutes` minutes.
    """
    while True:
        try:
            sessions_to_clean = session_manager.get_sessions_to_cleanup(hours_after_close=24)
            for session in sessions_to_clean:
                group_dir = os.path.join(UPLOADS_DIR, session.group_code)
                if os.path.exists(group_dir):
                    shutil.rmtree(group_dir)
                    logger.info(f"Cleaned up files for expired session: {session.group_code}")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

        await asyncio.sleep(interval_minutes * 60)


async def cleanup_session_files(group_code: str, delay_hours: int = 24):
    """
    Planifie le nettoyage des fichiers d'une session spécifique
    après un délai donné.
    """
    await asyncio.sleep(delay_hours * 3600)

    group_dir = os.path.join(UPLOADS_DIR, group_code)
    if os.path.exists(group_dir):
        try:
            shutil.rmtree(group_dir)
            logger.info(f"Scheduled cleanup completed for session: {group_code}")
        except Exception as e:
            logger.error(f"Failed to cleanup session {group_code}: {e}")
