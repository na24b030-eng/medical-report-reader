import json
import logging
from pathlib import Path
from functools import lru_cache
from typing import Dict, Any

from app.config import settings

logger = logging.getLogger(__name__)

@lru_cache(maxsize=1)
def load_catalog() -> Dict[str, Any]:
    catalog_path = Path(settings.MEDICAL_CATALOG_PATH)
    if catalog_path.exists():
        try:
            with open(catalog_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                logger.info("Catalog loaded: %d tests", len(data))
                return data
        except Exception as e:
            logger.error("Failed to load medical catalog: %s", e)
            return {}
    logger.warning("Medical catalog file not found at %s", catalog_path)
    return {}
