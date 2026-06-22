import logging
import time
import random
from typing import Dict, List, Any, Optional, Union
from urllib.parse import urlparse

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scraper_dashboard.scraper")

# Fallback user agents used when fake-useragent cannot fetch its remote database
_FALLBACK_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
]

try:
    from fake_useragent import UserAgent
    _UA_AVAILABLE = True
except ImportError:
    _UA_AVAILABLE = False

class BaseScraper:
    """
    Base class for all scraping engines.
    Provides shared features: User-Agent rotation, proxy handling, retry logic, rate-limiting, and logging.
    """

    def __init__(
        self,
        delay: float = 1.0,
        retries: int = 3,
        backoff_factor: float = 2.0,
        proxies: Optional[Union[str, List[str]]] = None,
        custom_ua: Optional[str] = None
    ):
        self.delay = delay
        self.retries = retries
        self.backoff_factor = backoff_factor
        self.custom_ua = custom_ua
        
        # Initialize fake-useragent with fallback
        self.ua_generator = None
        if _UA_AVAILABLE:
            try:
                self.ua_generator = UserAgent(fallback=random.choice(_FALLBACK_USER_AGENTS))
            except Exception:
                self.ua_generator = None
            
        # Initialize proxies
        self.proxy_list: List[str] = []
        if isinstance(proxies, str) and proxies.strip():
            self.proxy_list = [proxies.strip()]
        elif isinstance(proxies, list):
            self.proxy_list = [p.strip() for p in proxies if p.strip()]

    def get_user_agent(self) -> str:
        """Returns the configured custom User-Agent, or a random one from fake-useragent."""
        if self.custom_ua:
            return self.custom_ua
        if self.ua_generator:
            try:
                return self.ua_generator.random
            except Exception:
                pass
        # Always fall back to a hardcoded list — works on Render without network access
        return random.choice(_FALLBACK_USER_AGENTS)

    def get_random_proxy(self) -> Optional[str]:
        """Returns a random proxy from the list, or None if no proxies are configured."""
        if self.proxy_list:
            selected = random.choice(self.proxy_list)
            logger.info(f"Using proxy: {selected}")
            return selected
        return None

    def get_proxy_dict(self) -> Optional[Dict[str, str]]:
        """Returns requests-style proxy dict if a proxy is configured, or None."""
        proxy = self.get_random_proxy()
        if proxy:
            return {"http": proxy, "https": proxy}
        return None

    def validate_url(self, url: str) -> bool:
        """Validates that a string is a properly formatted HTTP/HTTPS URL."""
        if not url:
            return False
        try:
            parsed = urlparse(url)
            return all([parsed.scheme, parsed.netloc]) and parsed.scheme in ["http", "https"]
        except Exception:
            return False

    def execute_with_retry(self, func, *args, **kwargs) -> Any:
        """Executes a function with exponential backoff retry logic."""
        attempt = 1
        current_delay = self.delay

        while attempt <= self.retries:
            try:
                # Enforce politeness delay before executing
                if attempt > 1 or self.delay > 0:
                    sleep_time = current_delay if attempt > 1 else self.delay
                    logger.info(f"Politeness delay: sleeping for {sleep_time:.2f}s")
                    time.sleep(sleep_time)

                return func(*args, **kwargs)
                
            except Exception as e:
                logger.warning(
                    f"Attempt {attempt}/{self.retries} failed for {func.__name__}. Error: {e}"
                )
                if attempt == self.retries:
                    logger.error(f"All {self.retries} attempts failed.")
                    raise e
                
                # Calculate backoff delay
                current_delay *= self.backoff_factor
                # Add jitter
                current_delay += random.uniform(0, 1)
                attempt += 1

    def parse_rating_stars(self, rating_class: str) -> str:
        """Helper to convert textual book rating class (e.g. 'Three') to digit string '3'."""
        mapping = {
            "one": "1",
            "two": "2",
            "three": "3",
            "four": "4",
            "five": "5"
        }
        return mapping.get(str(rating_class).lower().strip(), "0")

    def scrape(self, url: str, max_pages: int = 1) -> List[Dict[str, Any]]:
        """
        Abstract/virtual method to run scraping task.
        Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement scrape().")
