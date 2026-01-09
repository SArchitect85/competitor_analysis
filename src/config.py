import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Base paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/fb_ad_library")

# Scraper delays (in seconds)
MIN_COMPETITOR_DELAY = int(os.getenv("MIN_COMPETITOR_DELAY", 30))
MAX_COMPETITOR_DELAY = int(os.getenv("MAX_COMPETITOR_DELAY", 60))
MIN_SCROLL_DELAY = int(os.getenv("MIN_SCROLL_DELAY", 2))
MAX_SCROLL_DELAY = int(os.getenv("MAX_SCROLL_DELAY", 5))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))

# Playwright
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
BROWSER_TIMEOUT = int(os.getenv("BROWSER_TIMEOUT", 60000))

# Media storage
MEDIA_BASE_PATH = Path(os.getenv("MEDIA_BASE_PATH", str(DATA_DIR / "media")))

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = Path(os.getenv("LOG_FILE", str(LOGS_DIR / "scraper.log")))

# Facebook Ad Library URLs
AD_LIBRARY_BASE_URL = "https://www.facebook.com/ads/library/"
AD_LIBRARY_SEARCH_URL = "https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country=ALL&view_all_page_id={page_id}&search_type=page&media_type=all"
