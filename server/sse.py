"""
sse.py — Gestionnaire Server-Sent Events pour le streaming temps réel.
"""

import asyncio
import json
import logging
import time
from typing import AsyncGenerator

logger = logging.getLogger(__name__)


class SSEManager:
    """
    Gère les connexions SSE par session (group_code).
    Chaque session a un ensemble de queues (une par client connecté au stream).
    """

    def __init__(self):
        # group_code -> list[asyncio.Queue]
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    def _get_subscribers(self, group_code: str) -> list[asyncio.Queue]:
        if group_code not in self._subscribers:
            self._subscribers[group_code] = []
        return self._subscribers[group_code]

    async def subscribe(self, group_code: str) -> AsyncGenerator[str, None]:
        """
        Souscrit au flux SSE d'une session.
        Yields des chaînes formatées SSE (data: ...\n\n).
        """
        queue: asyncio.Queue = asyncio.Queue()
        subscribers = self._get_subscribers(group_code)
        subscribers.append(queue)
        logger.info(f"SSE subscriber added for {group_code} (total: {len(subscribers)})")

        try:
            while True:
                try:
                    # Attendre un événement avec timeout pour le keepalive
                    data = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    # Envoyer keepalive
                    keepalive = json.dumps({"type": "keepalive"})
                    yield f"data: {keepalive}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if queue in subscribers:
                subscribers.remove(queue)
            logger.info(f"SSE subscriber removed for {group_code} (remaining: {len(subscribers)})")

    async def broadcast(self, group_code: str, event_data: dict):
        """Envoie un événement à tous les abonnés d'une session."""
        subscribers = self._get_subscribers(group_code)
        if not subscribers:
            return

        data_str = json.dumps(event_data)
        dead_queues = []

        for queue in subscribers:
            try:
                queue.put_nowait(data_str)
            except asyncio.QueueFull:
                dead_queues.append(queue)

        # Nettoyer les queues mortes
        for q in dead_queues:
            if q in subscribers:
                subscribers.remove(q)

    async def broadcast_status_update(self, group_code: str, clients_status: list[dict]):
        """Envoie un événement status_update avec le statut de tous les clients."""
        event = {
            "type": "status_update",
            "clients": clients_status,
        }
        await self.broadcast(group_code, event)

    def close_session_streams(self, group_code: str):
        """Ferme tous les flux SSE d'une session."""
        subscribers = self._subscribers.pop(group_code, [])
        for queue in subscribers:
            try:
                queue.put_nowait(json.dumps({"type": "session_closed"}))
            except asyncio.QueueFull:
                pass
        logger.info(f"Closed all SSE streams for session {group_code}")
