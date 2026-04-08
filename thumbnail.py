"""
thumbnail.py — Génération de miniatures avec Pillow.
"""

import logging
from PIL import Image

logger = logging.getLogger(__name__)


def generate_thumbnail(
    original_path: str,
    thumb_path: str,
    size: tuple = (320, 180),
    quality: int = 60,
) -> bool:
    """
    Génère une miniature JPEG à partir d'une image originale.

    Args:
        original_path: Chemin de l'image source.
        thumb_path: Chemin de destination de la miniature.
        size: Dimensions maximales (largeur, hauteur). Le ratio est conservé.
        quality: Qualité JPEG (1-100).

    Returns:
        True si la miniature a été générée avec succès, False sinon.
    """
    try:
        with Image.open(original_path) as img:
            img.thumbnail(size, Image.LANCZOS)
            # Convertir en RGB si nécessaire (ex: RGBA → RGB pour JPEG)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(thumb_path, "JPEG", quality=quality)
        logger.debug(f"Thumbnail generated: {thumb_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to generate thumbnail for {original_path}: {e}")
        return False
