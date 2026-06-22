import logging
from urllib.parse import urljoin, urlparse
from typing import Dict, List, Any
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from .base_scraper import BaseScraper

logger = logging.getLogger("scraper_dashboard.playwright_scraper")

_PAGE_TIMEOUT = 30000   # 30s per page navigation
_DETAIL_TIMEOUT = 20000 # 20s per detail page


class PlaywrightScraper(BaseScraper):
    """Playwright scraper — synchronous, headless Chromium."""

    def scrape(self, url: str, max_pages: int = 1) -> List[Dict[str, Any]]:
        if not self.validate_url(url):
            logger.error(f"Invalid URL: {url}")
            return []

        logger.info(f"Starting Playwright scraping for {url}")
        results = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox",
                          "--disable-dev-shm-usage", "--disable-gpu"]
                )
                proxy = self.get_random_proxy()
                ctx_args: dict = {
                    "user_agent": self.get_user_agent(),
                    "ignore_https_errors": True,
                }
                if proxy:
                    ctx_args["proxy"] = {"server": proxy}

                context = browser.new_context(**ctx_args)
                context.set_default_timeout(_PAGE_TIMEOUT)
                page = context.new_page()

                domain = urlparse(url).netloc
                if "books.toscrape.com" in domain:
                    results = self._scrape_books(page, url, max_pages)
                elif "demowebshop.tricentis.com" in domain:
                    results = self._scrape_demowebshop(page, url, max_pages)
                else:
                    results = self._scrape_generic(page, url, max_pages)

                browser.close()
        except Exception as e:
            logger.error(f"Playwright scraping failed: {e}")
            raise

        return results

    # =========================================================
    # BOOKS.TOSCRAPE.COM
    # =========================================================
    def _scrape_books(self, page, start_url: str, max_pages: int) -> List[Dict[str, Any]]:
        results = []
        current_url = start_url
        page_num = 1

        while current_url and page_num <= max_pages:
            logger.info(f"Playwright books page {page_num}: {current_url}")
            try:
                page.goto(current_url, wait_until="domcontentloaded", timeout=_PAGE_TIMEOUT)
                page.wait_for_selector("article.product_pod", timeout=10000)
            except PWTimeout:
                logger.warning(f"Timeout loading page {page_num}")
                break

            pods = page.locator("article.product_pod").all()
            if not pods:
                break

            page_data = []
            for pod in pods:
                try:
                    a = pod.locator("h3 a")
                    title = a.get_attribute("title") or ""
                    href = a.get_attribute("href") or ""
                    product_url = urljoin(current_url, href)
                    price = pod.locator(".price_color").inner_text().strip()
                    cls_str = pod.locator("p.star-rating").get_attribute("class") or ""
                    rating = next(
                        (self.parse_rating_stars(c) for c in cls_str.split() if c.lower() != "star-rating"), "0"
                    )
                    img_src = pod.locator("img").get_attribute("src") or ""
                    image_url = urljoin(current_url, img_src)
                    page_data.append({
                        "name": title, "price": price, "rating": rating,
                        "product_url": product_url, "image_url": image_url,
                        "category": "Books", "description": "",
                        "scraper_type": "playwright"
                    })
                except Exception as e:
                    logger.warning(f"Pod parse error: {e}")

            for item in page_data:
                page.wait_for_timeout(int(self.delay * 1000))
                try:
                    page.goto(item["product_url"], wait_until="domcontentloaded", timeout=_DETAIL_TIMEOUT)
                    crumbs = page.locator("ul.breadcrumb li").all()
                    if len(crumbs) >= 3:
                        item["category"] = crumbs[2].inner_text().strip()
                    desc = page.locator("#product_description + p")
                    item["description"] = desc.inner_text().strip() if desc.count() > 0 else ""
                except PWTimeout:
                    logger.warning(f"Timeout on detail page: {item['product_url']}")
                    item["description"] = ""
                except Exception as e:
                    logger.warning(f"Detail error: {e}")
                    item["description"] = ""
                results.append(item)

            if page_num < max_pages:
                try:
                    page.goto(current_url, wait_until="domcontentloaded", timeout=_PAGE_TIMEOUT)
                    nxt = page.locator("li.next a")
                    if nxt.count() > 0:
                        current_url = urljoin(current_url, nxt.get_attribute("href"))
                        page_num += 1
                    else:
                        break
                except Exception:
                    break
            else:
                break

        return results

    # =========================================================
    # DEMOWEBSHOP
    # =========================================================
    def _scrape_demowebshop(self, page, start_url: str, max_pages: int) -> List[Dict[str, Any]]:
        results = []
        current_url = start_url
        page_num = 1

        while current_url and page_num <= max_pages:
            logger.info(f"Playwright demowebshop page {page_num}")
            try:
                page.goto(current_url, wait_until="domcontentloaded", timeout=_PAGE_TIMEOUT)
                page.wait_for_selector(".product-item", timeout=10000)
            except PWTimeout:
                break

            page_data = []
            for item in page.locator(".product-item").all():
                try:
                    a = item.locator(".product-title a")
                    name = a.inner_text().strip()
                    product_url = urljoin(current_url, a.get_attribute("href") or "")
                    price_el = item.locator(".product-price, .actual-price").first
                    price = price_el.inner_text().strip() if price_el.count() > 0 else "0.00"
                    page_data.append({
                        "name": name, "price": price, "product_url": product_url,
                        "rating": "0", "category": "Products", "description": "",
                        "image_url": "", "scraper_type": "playwright"
                    })
                except Exception as e:
                    logger.warning(f"Item parse error: {e}")

            for item in page_data:
                page.wait_for_timeout(int(self.delay * 1000))
                try:
                    page.goto(item["product_url"], wait_until="domcontentloaded", timeout=_DETAIL_TIMEOUT)
                    crumbs = page.locator(".breadcrumb a").all()
                    if crumbs:
                        item["category"] = crumbs[-1].inner_text().strip()
                    for sel in [".full-description", ".short-description"]:
                        el = page.locator(sel)
                        if el.count() > 0:
                            item["description"] = el.inner_text().strip()
                            break
                    img = page.locator(".gallery img").first
                    if img.count() > 0:
                        item["image_url"] = urljoin(item["product_url"], img.get_attribute("src") or "")
                    rating_el = page.locator(".rating div").first
                    if rating_el.count() > 0:
                        style = rating_el.get_attribute("style") or ""
                        if "width:" in style:
                            w = style.replace("width:", "").replace("%", "").replace(";", "").strip()
                            item["rating"] = str(round(float(w) / 20.0, 1))
                except PWTimeout:
                    logger.warning(f"Timeout on {item['product_url']}")
                except Exception as e:
                    logger.warning(f"Detail error: {e}")
                results.append(item)

            if page_num < max_pages:
                try:
                    page.goto(current_url, wait_until="domcontentloaded", timeout=_PAGE_TIMEOUT)
                    nxt = page.locator("li.next-page a")
                    if nxt.count() > 0:
                        current_url = urljoin(current_url, nxt.get_attribute("href"))
                        page_num += 1
                    else:
                        break
                except Exception:
                    break
            else:
                break

        return results

    # =========================================================
    # GENERIC
    # =========================================================
    def _scrape_generic(self, page, start_url: str, max_pages: int) -> List[Dict[str, Any]]:
        results = []
        current_url = start_url
        page_num = 1

        while current_url and page_num <= max_pages:
            logger.info(f"Playwright generic page {page_num}")
            try:
                page.goto(current_url, wait_until="domcontentloaded", timeout=_PAGE_TIMEOUT)
            except PWTimeout:
                break

            cards = []
            for sel in ["article", ".product-card", ".product-item", ".card", ".item-box"]:
                elems = page.locator(sel).all()
                if len(elems) >= 3:
                    cards = elems
                    break
            if not cards:
                cards = [a for a in page.locator("a").all() if a.inner_text().strip()][:30]
            if not cards:
                break

            for card in cards:
                try:
                    title_el = card.locator("h1,h2,h3,h4,.title,.name").first
                    name = title_el.inner_text().strip() if title_el.count() > 0 else card.inner_text().strip().split("\n")[0][:60]
                    if not name or len(name) < 3:
                        continue
                    price_el = card.locator(".price,.amount,[class*='price']").first
                    price = price_el.inner_text().strip() if price_el.count() > 0 else "$0.00"
                    img_el = card.locator("img").first
                    image_url = urljoin(current_url, img_el.get_attribute("src") or "") if img_el.count() > 0 else ""
                    href = card.get_attribute("href")
                    if not href:
                        link = card.locator("a").first
                        href = link.get_attribute("href") if link.count() > 0 else None
                    product_url = urljoin(current_url, href) if href else current_url
                    results.append({
                        "name": name, "price": price, "product_url": product_url,
                        "rating": "3.0", "category": "Generic",
                        "description": "Generic scraped item.",
                        "image_url": image_url, "scraper_type": "playwright"
                    })
                except Exception as e:
                    logger.warning(f"Generic parse error: {e}")

            nxt = page.locator("a:has-text('next'), a:has-text('Next'), a:has-text('>'), a:has-text('»')").first
            if nxt.count() > 0 and nxt.is_visible():
                href = nxt.get_attribute("href")
                if href:
                    current_url = urljoin(current_url, href)
                    page_num += 1
                else:
                    break
            else:
                break

        return results
