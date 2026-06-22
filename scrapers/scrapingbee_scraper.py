"""
ScrapingBee-based scraper — uses a cloud browser API instead of a local Chrome.
Works on Render and any serverless environment.

Free tier: 150 credits/month at https://app.scrapingbee.com/
Set SCRAPINGBEE_API_KEY in your environment variables.
"""
import logging
import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import Dict, List, Any, Optional
from .base_scraper import BaseScraper

logger = logging.getLogger("scraper_dashboard.scrapingbee_scraper")

_API_URL = "https://app.scrapingbee.com/api/v1/"


class ScrapingBeeScraper(BaseScraper):
    """
    Scraper that uses ScrapingBee cloud browser API.
    Behaves like Selenium/Playwright but runs on any server.
    Falls back to direct requests if API key is not configured.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.api_key = os.getenv("SCRAPINGBEE_API_KEY", "")
        if not self.api_key:
            logger.warning("SCRAPINGBEE_API_KEY not set — falling back to direct requests (no JS rendering)")

    def _fetch(self, url: str, render_js: bool = True) -> str:
        """Fetch a URL via ScrapingBee API or direct requests."""
        if not self.api_key:
            # No API key — use plain requests
            headers = {"User-Agent": self.get_user_agent()}
            resp = requests.get(url, headers=headers, timeout=20)
            if resp.encoding and resp.encoding.lower() in ("iso-8859-1", "latin-1"):
                resp.encoding = resp.apparent_encoding
            resp.raise_for_status()
            return resp.text

        params = {
            "api_key": self.api_key,
            "url": url,
            "render_js": "true" if render_js else "false",
            "premium_proxy": "false",
            "country_code": "us",
        }
        resp = requests.get(_API_URL, params=params, timeout=60)
        resp.raise_for_status()
        return resp.text

    def scrape(self, url: str, max_pages: int = 1) -> List[Dict[str, Any]]:
        if not self.validate_url(url):
            logger.error(f"Invalid URL: {url}")
            return []

        domain = urlparse(url).netloc
        logger.info(f"ScrapingBee scraping {url} (api_key={'set' if self.api_key else 'NOT SET'})")

        if "books.toscrape.com" in domain:
            return self._scrape_books(url, max_pages)
        elif "demowebshop.tricentis.com" in domain:
            return self._scrape_demowebshop(url, max_pages)
        else:
            return self._scrape_generic(url, max_pages)

    def _scrape_books(self, start_url: str, max_pages: int) -> List[Dict[str, Any]]:
        results = []
        current_url = start_url
        page_num = 1

        while current_url and page_num <= max_pages:
            logger.info(f"ScrapingBee books page {page_num}: {current_url}")
            try:
                html = self._fetch(current_url, render_js=False)  # static site
                soup = BeautifulSoup(html, "html.parser")
                pods = soup.select("article.product_pod")
                if not pods:
                    break

                for pod in pods:
                    try:
                        href = pod.h3.a["href"]
                        product_url = urljoin(current_url, href)
                        title = pod.h3.a["title"]
                        price = pod.select_one(".price_color").text.strip()
                        rating_cls = pod.select_one("p.star-rating")["class"]
                        rating = next((self.parse_rating_stars(c) for c in rating_cls if c.lower() != "star-rating"), "0")
                        img_src = pod.img["src"]
                        image_url = urljoin(current_url, img_src)

                        # Get detail page
                        detail = self._get_book_detail(product_url)
                        results.append({
                            "name": title,
                            "price": price,
                            "rating": rating,
                            "product_url": product_url,
                            "image_url": image_url,
                            "category": detail.get("category", "Books"),
                            "description": detail.get("description", ""),
                            "scraper_type": "scrapingbee",
                        })
                    except Exception as e:
                        logger.warning(f"Pod parse error: {e}")

                nxt = soup.select_one("li.next a")
                if nxt and page_num < max_pages:
                    current_url = urljoin(current_url, nxt["href"])
                    page_num += 1
                else:
                    break
            except Exception as e:
                logger.error(f"Books page {page_num} failed: {e}")
                break

        return results

    def _get_book_detail(self, url: str) -> Dict[str, str]:
        try:
            html = self._fetch(url, render_js=False)
            soup = BeautifulSoup(html, "html.parser")
            crumbs = soup.select("ul.breadcrumb li")
            category = crumbs[2].text.strip() if len(crumbs) >= 3 else "Books"
            desc_tag = soup.select_one("#product_description")
            description = desc_tag.find_next("p").text.strip() if desc_tag else ""
            return {"category": category, "description": description}
        except Exception:
            return {}

    def _scrape_demowebshop(self, start_url: str, max_pages: int) -> List[Dict[str, Any]]:
        results = []
        current_url = start_url
        page_num = 1

        while current_url and page_num <= max_pages:
            try:
                html = self._fetch(current_url, render_js=True)
                soup = BeautifulSoup(html, "html.parser")
                boxes = soup.select(".product-grid .item-box, .product-list .item-box, .product-item")
                if not boxes:
                    break

                for box in boxes:
                    try:
                        a = box.select_one(".product-title a")
                        if not a:
                            continue
                        name = a.text.strip()
                        product_url = urljoin(current_url, a["href"])
                        price_el = box.select_one(".product-price, .actual-price")
                        price = price_el.text.strip() if price_el else "0.00"
                        results.append({
                            "name": name, "price": price,
                            "product_url": product_url,
                            "rating": "0", "category": "Products",
                            "description": "", "image_url": "",
                            "scraper_type": "scrapingbee",
                        })
                    except Exception as e:
                        logger.warning(f"Item error: {e}")

                nxt = soup.select_one("li.next-page a")
                if nxt and page_num < max_pages:
                    current_url = urljoin(current_url, nxt["href"])
                    page_num += 1
                else:
                    break
            except Exception as e:
                logger.error(f"DemoWebShop page {page_num} failed: {e}")
                break

        return results

    def _scrape_generic(self, start_url: str, max_pages: int) -> List[Dict[str, Any]]:
        results = []
        current_url = start_url
        page_num = 1

        while current_url and page_num <= max_pages:
            try:
                html = self._fetch(current_url, render_js=True)
                soup = BeautifulSoup(html, "html.parser")

                cards = []
                for sel in [".product-card", ".product-item", ".card", "article", ".item-box"]:
                    cards = soup.select(sel)
                    if len(cards) >= 3:
                        break
                if not cards:
                    break

                for card in cards:
                    try:
                        name_el = card.select_one("h1,h2,h3,h4,.title,.name")
                        name = name_el.text.strip() if name_el else card.text.strip().split("\n")[0][:60]
                        if not name or len(name) < 3:
                            continue
                        price_el = card.select_one(".price,.amount,[class*='price']")
                        price = price_el.text.strip() if price_el else "$0.00"
                        img = card.find("img")
                        image_url = urljoin(current_url, img["src"]) if img else ""
                        a = card.find("a", href=True)
                        product_url = urljoin(current_url, a["href"]) if a else current_url
                        results.append({
                            "name": name, "price": price,
                            "product_url": product_url,
                            "rating": "3.0", "category": "Generic",
                            "description": "Cloud-scraped item.",
                            "image_url": image_url,
                            "scraper_type": "scrapingbee",
                        })
                    except Exception as e:
                        logger.warning(f"Card error: {e}")
                break  # Generic: one page only
            except Exception as e:
                logger.error(f"Generic page {page_num} failed: {e}")
                break

        return results
