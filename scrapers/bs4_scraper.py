import logging
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import Dict, List, Any, Optional
from .base_scraper import BaseScraper

logger = logging.getLogger("scraper_dashboard.bs4_scraper")

class BS4Scraper(BaseScraper):
    """
    Scraper using Requests and BeautifulSoup.
    Optimized for books.toscrape.com and demowebshop.tricentis.com with generic fallback.
    """

    def _get_page_content(self, url: str) -> str:
        """Helper to fetch raw page HTML using requests."""
        headers = {"User-Agent": self.get_user_agent()}
        proxies = self.get_proxy_dict()
        
        def make_request():
            response = requests.get(url, headers=headers, proxies=proxies, timeout=20)
            response.raise_for_status()
            # Detect encoding properly to avoid garbled characters (e.g. Â£ instead of £)
            if response.encoding and response.encoding.lower() in ("iso-8859-1", "latin-1"):
                response.encoding = response.apparent_encoding
            return response.text

        return self.execute_with_retry(make_request)

    def scrape(self, url: str, max_pages: int = 1) -> List[Dict[str, Any]]:
        if not self.validate_url(url):
            logger.error(f"Invalid URL provided: {url}")
            return []

        domain = urlparse(url).netloc
        logger.info(f"Starting BS4 scraping for {url} on domain: {domain}")

        if "books.toscrape.com" in domain:
            return self._scrape_books(url, max_pages)
        elif "demowebshop.tricentis.com" in domain:
            return self._scrape_demowebshop(url, max_pages)
        else:
            return self._scrape_generic(url, max_pages)

    # =====================================================================
    # BOOKS TO SCRAPE SPECIALIZED SCRAPER
    # =====================================================================
    def _scrape_books(self, start_url: str, max_pages: int) -> List[Dict[str, Any]]:
        results = []
        current_url = start_url
        page_num = 1

        while current_url and page_num <= max_pages:
            logger.info(f"BS4 books.toscrape: Scraping page {page_num}: {current_url}")
            try:
                html = self._get_page_content(current_url)
                soup = BeautifulSoup(html, "html.parser")
                book_pods = soup.select("article.product_pod")

                if not book_pods:
                    logger.warning(f"No products found on page {page_num}")
                    break

                for pod in book_pods:
                    # Get product url
                    href = pod.h3.a["href"]
                    # books.toscrape relative links can be complex depending on which page we are on
                    product_url = urljoin(current_url, href)
                    
                    # We fetch details for description and category
                    product_details = self._scrape_book_details(product_url)
                    
                    # Basic listing data
                    title = pod.h3.a["title"]
                    price = pod.select_one(".price_color").text.strip()
                    
                    rating_classes = pod.select_one("p.star-rating")["class"]
                    rating_star = "0"
                    for cls in rating_classes:
                        if cls.lower() != "star-rating":
                            rating_star = self.parse_rating_stars(cls)

                    image_src = pod.img["src"]
                    image_url = urljoin(current_url, image_src)

                    book_info = {
                        "name": title,
                        "price": price,
                        "rating": rating_star,
                        "description": product_details.get("description", ""),
                        "category": product_details.get("category", "Books"),
                        "product_url": product_url,
                        "image_url": image_url,
                        "scraper_type": "bs4"
                    }
                    results.append(book_info)

                # Pagination: Find next button
                next_button = soup.select_one("li.next a")
                if next_button:
                    next_href = next_button["href"]
                    current_url = urljoin(current_url, next_href)
                    page_num += 1
                else:
                    logger.info("No next page found (reached end of pagination).")
                    break

            except Exception as e:
                logger.error(f"Error scraping books list page {page_num}: {e}")
                break

        return results

    def _scrape_book_details(self, url: str) -> Dict[str, str]:
        """Fetches description and category from book detail page."""
        try:
            html = self._get_page_content(url)
            soup = BeautifulSoup(html, "html.parser")
            
            # Extract category from breadcrumb (usually 3rd element)
            category = "Books"
            breadcrumbs = soup.select("ul.breadcrumb li")
            if len(breadcrumbs) >= 3:
                category = breadcrumbs[2].text.strip()

            # Extract description
            description = ""
            desc_tag = soup.select_one("#product_description")
            if desc_tag:
                desc_p = desc_tag.find_next("p")
                if desc_p:
                    description = desc_p.text.strip()
            
            return {"category": category, "description": description}
        except Exception as e:
            logger.warning(f"Failed to scrape book details from {url}: {e}")
            return {}

    # =====================================================================
    # DEMO WEBSHOP SPECIALIZED SCRAPER
    # =====================================================================
    def _scrape_demowebshop(self, start_url: str, max_pages: int) -> List[Dict[str, Any]]:
        results = []
        current_url = start_url
        page_num = 1

        while current_url and page_num <= max_pages:
            logger.info(f"BS4 demowebshop: Scraping page {page_num}: {current_url}")
            try:
                html = self._get_page_content(current_url)
                soup = BeautifulSoup(html, "html.parser")
                
                # Check for products
                item_boxes = soup.select(".product-grid .item-box, .product-list .item-box")
                if not item_boxes:
                    # Fallback standard selector
                    item_boxes = soup.select(".product-item")

                if not item_boxes:
                    logger.warning(f"No products found on Demo Web Shop page {page_num}")
                    break

                for box in item_boxes:
                    title_link = box.select_one(".product-title a")
                    if not title_link:
                        continue
                    
                    product_url = urljoin(current_url, title_link["href"])
                    
                    # Fetch detailed info (e.g. image, description, rating percentage)
                    details = self._scrape_demowebshop_details(product_url)
                    
                    name = title_link.text.strip()
                    price = "0.00"
                    price_tag = box.select_one(".product-price") or box.select_one(".actual-price")
                    if price_tag:
                        price = price_tag.text.strip()

                    product_info = {
                        "name": name,
                        "price": price,
                        "rating": details.get("rating", "0"),
                        "description": details.get("description", ""),
                        "category": details.get("category", "Products"),
                        "product_url": product_url,
                        "image_url": details.get("image_url", ""),
                        "scraper_type": "bs4"
                    }
                    results.append(product_info)

                # Pagination: Find 'Next' page link
                next_page = soup.select_one("li.next-page a")
                if next_page:
                    current_url = urljoin(current_url, next_page["href"])
                    page_num += 1
                else:
                    break
            except Exception as e:
                logger.error(f"Error scraping Demo Webshop page {page_num}: {e}")
                break

        return results

    def _scrape_demowebshop_details(self, url: str) -> Dict[str, str]:
        """Fetches product details for demowebshop."""
        try:
            html = self._get_page_content(url)
            soup = BeautifulSoup(html, "html.parser")
            
            # Category from breadcrumb
            category = "Products"
            breadcrumbs = soup.select(".breadcrumb a")
            if breadcrumbs:
                category = breadcrumbs[-1].text.strip()
                
            # Description
            description = ""
            desc_tag = soup.select_one(".full-description")
            if desc_tag:
                description = desc_tag.text.strip()
            else:
                desc_tag_short = soup.select_one(".short-description")
                if desc_tag_short:
                    description = desc_tag_short.text.strip()
                    
            # Image URL
            image_url = ""
            img_tag = soup.select_one(".gallery img")
            if img_tag:
                image_url = urljoin(url, img_tag["src"])

            # Rating
            rating = "0"
            rating_tag = soup.select_one(".rating div")
            if rating_tag and rating_tag.get("style"):
                style_str = rating_tag["style"]
                # Style looks like "width: 80%"
                if "width:" in style_str:
                    width = style_str.replace("width:", "").replace("%", "").replace(";", "").strip()
                    # Convert to scale of 0-5
                    try:
                        rating = str(round(float(width) / 20.0, 1))
                    except ValueError:
                        rating = "0"
                        
            return {
                "category": category,
                "description": description,
                "image_url": image_url,
                "rating": rating
            }
        except Exception as e:
            logger.warning(f"Failed to scrape demowebshop details from {url}: {e}")
            return {}

    # =====================================================================
    # GENERIC HEURISTIC SCRAPER (FALLBACK)
    # =====================================================================
    def _scrape_generic(self, start_url: str, max_pages: int) -> List[Dict[str, Any]]:
        results = []
        current_url = start_url
        page_num = 1

        while current_url and page_num <= max_pages:
            logger.info(f"BS4 generic fallback: Scraping page {page_num}: {current_url}")
            try:
                html = self._get_page_content(current_url)
                soup = BeautifulSoup(html, "html.parser")
                
                # Heuristic 1: Find articles, cards, product containers
                # Common classes for grid items/cards
                card_selectors = [
                    ".product-card", ".product-item", ".card", ".item-box", 
                    "article", ".product", ".g-col", ".grid-item"
                ]
                
                cards = []
                for sel in card_selectors:
                    cards = soup.select(sel)
                    if len(cards) >= 3: # found a pattern of cards
                        logger.info(f"Found cards using selector: {sel}")
                        break
                
                # If cards not found, try to locate anchors that might be products
                if not cards:
                    cards = soup.find_all("a", href=True)
                    # Filter down anchors with images or price-like elements inside
                    cards = [c for c in cards if c.find("img") or any(char.isdigit() for char in c.text)]
                    cards = cards[:30] # Limit to top 30
                    
                if not cards:
                    logger.warning("Could not identify any product items on page.")
                    break

                for i, card in enumerate(cards):
                    # Find Product Name
                    name = ""
                    name_tags = card.select("h1, h2, h3, h4, .title, .name, [class*='title'], [class*='name']")
                    if name_tags:
                        name = name_tags[0].text.strip()
                    else:
                        name = card.text.strip().split("\n")[0][:60] # best effort
                        
                    if not name or len(name) < 3:
                        continue # skip empty tags
                        
                    # Find Price
                    price = ""
                    price_tags = card.select(".price, .amount, [class*='price'], [class*='amount']")
                    if price_tags:
                        price = price_tags[0].text.strip()
                    else:
                        # Scan all text in card for currency symbols ($, £, €, Rs)
                        price_match = re.search(r"([$£€¥]|Rs\.?)\s?\d+([.,]\d{2})?", card.text)
                        if price_match:
                            price = price_match.group(0)

                    # Find Image URL
                    image_url = ""
                    img_tags = card.find_all("img")
                    if img_tags:
                        src = img_tags[0].get("src") or img_tags[0].get("data-src")
                        if src:
                            image_url = urljoin(current_url, src)

                    # Find Product URL
                    product_url = current_url
                    links = card.find_all("a", href=True)
                    if links:
                        product_url = urljoin(current_url, links[0]["href"])
                    elif card.name == "a" and card.get("href"):
                        product_url = urljoin(current_url, card["href"])

                    product_info = {
                        "name": name,
                        "price": price or "$0.00",
                        "rating": "3.0", # default mock
                        "description": "Generic scraped product details.",
                        "category": "Generic",
                        "product_url": product_url,
                        "image_url": image_url,
                        "scraper_type": "bs4"
                    }
                    results.append(product_info)

                # Heuristic for Next Page pagination
                next_tag = soup.find("a", text=re.compile(r"next|Next|>|»", re.IGNORECASE))
                if next_tag and next_tag.get("href"):
                    current_url = urljoin(current_url, next_tag["href"])
                    page_num += 1
                else:
                    break

            except Exception as e:
                logger.error(f"Error in generic scraper at page {page_num}: {e}")
                break

        return results
