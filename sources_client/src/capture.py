import mss
import mss.tools
from datetime import datetime
import os
import logging

logger = logging.getLogger(__name__)

def take_screenshot(output_path):
    """
    Takes a screenshot of all monitors and saves it as PNG.
    Returns the absolute path of the saved file.
    """
    try:
        with mss.mss() as sct:
            # monitors[0] is the virtual monitor encompassing all screens
            monitor = sct.monitors[0]
            img = sct.grab(monitor)
            mss.tools.to_png(img.rgb, img.size, output=output_path)
    except Exception as e:
        logger.warning(f"Screen capture failed: {e}. Falling back to placeholder.")
        # Fallback for headless environments: create a blue placeholder image
        try:
            from PIL import Image, ImageDraw
            img = Image.new('RGB', (800, 600), color=(73, 109, 137))
            d = ImageDraw.Draw(img)
            d.text((20, 250), f"Headless Capture\n{datetime.now().isoformat()}\nError: {str(e)[:80]}", fill=(255, 255, 0))
            img.save(output_path)
        except Exception as pil_err:
            logger.error(f"Fallback placeholder also failed: {pil_err}")

    return os.path.abspath(output_path)

def generate_filename(temp_dir):
    """
    Generates a unique filename for a screenshot based on the current timestamp.
    """
    os.makedirs(temp_dir, exist_ok=True)
    timestamp = datetime.now().isoformat().replace(':', '-')
    return os.path.join(temp_dir, f"screenshot_{timestamp}.png")
