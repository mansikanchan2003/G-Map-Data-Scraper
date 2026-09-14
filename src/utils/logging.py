import logging
import sys
from src.config import settings

def setup_logging():
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    
    # Configure root logger
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

    # Silence chatty libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger("gmap_scraper")
