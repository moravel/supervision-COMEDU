"""
queue_manager.py — Gestion de la file d'attente locale pour les screenshots.

Stocke les captures non envoyées sur disque et les retransmet 
dès que le serveur est joignable. Throttle à MAX_ITEMS_PER_CYCLE.
"""

import os
import json
import logging
import time
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)

# Maximum d'éléments traités par cycle pour ne pas saturer le réseau
MAX_ITEMS_PER_CYCLE = 3


class QueueManager:
    def __init__(self, config):
        self.config = config
        self.temp_dir = config['temp_dir']
        self.queue_file = os.path.join(self.temp_dir, 'queue.json')
        self.queue = self._load_queue()

    def _load_queue(self):
        if os.path.exists(self.queue_file):
            try:
                with open(self.queue_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load queue.json: {e}")
        return []

    def _save_queue(self):
        try:
            with open(self.queue_file, 'w') as f:
                json.dump(self.queue, f)
        except Exception as e:
            logger.error(f"Failed to save queue.json: {e}")

    def add_to_queue(self, screenshot_path, timestamp=None):
        if not timestamp:
            timestamp = datetime.now().isoformat()

        item = {
            "path": screenshot_path,
            "timestamp": timestamp,
            "retries": 0,
            "next_retry": time.time(),
        }
        self.queue.append(item)
        self._save_queue()
        logger.info(f"Added to queue: {screenshot_path}")

    async def process_queue(self, upload_func, login, group_code):
        """
        Traite la file d'attente.
        Maximum MAX_ITEMS_PER_CYCLE éléments par appel.

        Args:
            upload_func: Fonction async d'upload (config, login, group_code, path, timestamp)
            login: Login de l'élève
            group_code: Code groupe de la session
        """
        if not self.queue:
            return

        current_time = time.time()
        items_to_process = [
            item for item in self.queue if item['next_retry'] <= current_time
        ]

        # Throttle : max N éléments par cycle
        items_to_process = items_to_process[:MAX_ITEMS_PER_CYCLE]

        for item in items_to_process:
            result = await upload_func(
                self.config, login, group_code,
                item['path'], item['timestamp'],
            )

            if isinstance(result, dict):
                # Succès
                self.queue.remove(item)
                if os.path.exists(item['path']):
                    os.remove(item['path'])
                logger.info(f"Processed from queue: {item['path']}")
            elif isinstance(result, str):
                # Erreur HTTP fatale → vider la queue
                logger.warning(f"Fatal error {result} during queue processing. Clearing queue.")
                self.queue.clear()
                break
            else:
                # Erreur réseau → retry avec backoff
                item['retries'] += 1
                if item['retries'] >= self.config['retry_policy']['max_retries']:
                    logger.warning(f"Max retries for {item['path']}. Removing.")
                    self.queue.remove(item)
                    if os.path.exists(item['path']):
                        os.remove(item['path'])
                else:
                    backoff = min(
                        self.config['retry_policy']['initial_backoff_s'] * (2 ** (item['retries'] - 1)),
                        self.config['retry_policy']['max_backoff_s'],
                    )
                    item['next_retry'] = current_time + backoff
                    logger.info(f"Retrying {item['path']} in {backoff}s (attempt {item['retries']})")

        self._save_queue()
        self.cleanup_storage()

    def cleanup_storage(self):
        """Ne dépasse pas max_local_storage_mb."""
        max_bytes = self.config['max_local_storage_mb'] * 1024 * 1024
        current_size = 0
        files = []

        for f in os.listdir(self.temp_dir):
            if f.endswith('.png'):
                full_path = os.path.join(self.temp_dir, f)
                size = os.path.getsize(full_path)
                files.append((full_path, size, os.path.getmtime(full_path)))
                current_size += size

        if current_size > max_bytes:
            logger.info("Storage limit exceeded. Cleaning up.")
            files.sort(key=lambda x: x[2])
            for path, size, mtime in files:
                os.remove(path)
                current_size -= size
                self.queue = [item for item in self.queue if item['path'] != path]
                if current_size <= max_bytes * 0.9:
                    break
            self._save_queue()
