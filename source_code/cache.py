"""
Simple JSON file cache for extraction results.

Each image gets a corresponding .json file in the cache directory. This enables:
- Resume after failure (don't re-process images 1-5000 if image 5001 fails)
- Incremental processing (only process newly added images)
- No wasted API calls on re-runs
"""

import json
import logging
from pathlib import Path

from source_code.config import CACHE_DIR

logger = logging.getLogger(__name__)


def _cache_path(image_name: str) -> Path:
    """
    Return the cache file path for a given image name.

    :param image_name: Filename of the source image (e.g. "product_01.png").
    :return: Path to the corresponding JSON cache file.
    """
    return Path(CACHE_DIR) / f"{image_name}.json"


def get_cached_result(image_name: str) -> dict | None:
    """
    Load a previously cached extraction result for an image.

    :param image_name: Filename of the source image.
    :return: Parsed extraction dict, or None if no valid cache exists.
    """
    path = _cache_path(image_name)
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Corrupt cache for {image_name}, will re-process: {e}")
        return None


def save_result(image_name: str, result: dict) -> None:
    """
    Persist an extraction result to the cache as a JSON file.

    :param image_name: Filename of the source image.
    :param result: Extraction result dict to cache.
    :return: None.
    """
    Path(CACHE_DIR).mkdir(exist_ok=True)
    path = _cache_path(image_name)
    with open(path, "w") as f:
        json.dump(result, f, indent=2)


def clear_cache() -> None:
    """
    Remove all cached extraction results from the cache directory.

    :return: None.
    """
    cache_dir = Path(CACHE_DIR)
    if cache_dir.exists():
        for path in cache_dir.glob("*.json"):
            path.unlink()
        logger.info("Cache cleared")
