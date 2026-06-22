import logging
import asyncio
from urllib.parse import urljoin, urlparse
from typing import Dict, List, Any, Optional
from playwright.sync_api import sync_playwright
from playwright.async_api import async_playwright
from .base_scraper import BaseScraper

logger = logging.getLogger("scraper_dashboard.playwright_scraper")

class PlaywrightScraper(BaseScraper):
    """
    Playwright scraper supporting both synchronous scraping (for Streamlit UI) 
    and asynchronous scraping (for FastAPI/high-throughput runs).
    """

    # =====================================================================
    # SYNCHRONOUS PLAYWRIGHT SCRAPING
    # =====================================================================
    def scrape(self, url: str, max_pages: int = 1) -> List[Dict[str, Any]]:
        if not self.validate_url(url):
            logger.error(f"Invalid URL: {url}")
            return []

        logger.info(f"Starting Playwright (Sync) scraping for {url}")
        results = []
        
        try:
            with sync_playwright() as p:
                browser_args = ["--no-sandbox", "--disable-setuid-sandbox"]
                
                proxy_server = self.get_random_proxy()
                proxy_config = None
                if proxy_server:
                    proxy_config = {"server": proxy_server}

                browser = p.chromium.launch(headless=True, args=browser_args)
                
                context_args = {
                    "user_agent": self.get_user_agent(),
                    "ignore_https_errors": True
                }
                if proxy_config:
                    context_args["proxy"] = proxy_config

                context = browser.new_context(**context_args)
                page = context.new_page()

                # Enable route blocking for optimization
                page.route("**/*.{css,png,jpg,jpeg,gif,svg,woff,woff2,ttf}", lambda route: route.abort() if "image" not in route.request.resource_type else route.continue_())

                domain = urlparse(url).netloc
                if "books.toscrape.com" in domain:
                    results = self._scrape_books_sync(page, url, max_pages)
                elif "demowebshop.tricentis.com" in domain:
                    results = self._scrape_demowebshop_sync(page, url, max_pages)
                else:
                    results = self._scrape_generic_sync(page, url, max_pages)

                browser.close()
        except Exception as e:
            logger.error(f"Playwright Sync Scraping failed: {e}")

        return results

    def _scrape_books_sync(self, page, start_url: str, max_pages: int) -> List[Dict[str, Any]]:
        results = []
        current_url = start_url
        page_num = 1

        while current_url and page_num <= max_pages:
            logger.info(f"Playwright books.toscrape: Scraping page {page_num}: {current_url}")
            try:
                page.goto(current_url, wait_until="domcontentloaded")
                
                # Extract all pod elements
                pods = page.locator("article.product_pod").all()
                if not pods:
                    break

                page_data = []
                for pod in pods:
                    # Get details available in page list
                    title_link = pod.locator("h3 a")
                    title = title_link.get_attribute("title")
                    href = title_link.get_attribute("href")
                    product_url = urljoin(current_url, href)

                    price = pod.locator(".price_color").inner_text().strip()
                    
                    rating_classes = pod.locator("p.star-rating").get_attribute("class").split()
                    rating_star = "0"
                    for cls in rating_classes:
                        if cls.lower() != "star-rating":
                            rating_star = self.parse_rating_stars(cls)

                    image_src = pod.locator("img").get_attribute("src")
                    image_url = urljoin(current_url, image_src)

                    page_data.append({
                        "name": title,
                        "price": price,
                        "rating": rating_star,
                        "product_url": product_url,
                        "image_url": image_url,
                        "category": "Books",
                        "scraper_type": "playwright"
                    })

                # Go into each book detail to extract category and description
                for item in page_data:
                    # Politeness delay
                    page.wait_for_timeout(int(self.delay * 1000))
                    try:
                        page.goto(item["product_url"], wait_until="domcontentloaded")
                        
                        # Category breadcrumb
                        breadcrumbs = page.locator("ul.breadcrumb li").all()
                        if len(breadcrumbs) >= 3:
                            item["category"] = breadcrumbs[2].inner_text().strip()

                        # Description
                        desc_header = page.locator("#product_description")
                        if desc_header.count() > 0:
                            desc_p = page.locator("#product_description + p")
                            item["description"] = desc_p.inner_text().strip()
                        else:
                            item["description"] = ""
                            
                        results.append(item)
                    except Exception as e:
                        logger.warning(f"Error fetching details: {e}")
                        item["description"] = ""
                        results.append(item)

                # Return to page to find pagination
                if page_num < max_pages:
                    page.goto(current_url, wait_until="domcontentloaded")
                    next_button = page.locator("li.next a")
                    if next_button.count() > 0:
                        current_url = urljoin(current_url, next_button.get_attribute("href"))
                        page_num += 1
                    else:
                        break
                else:
                    break
            except Exception as e:
                logger.error(f"Error books sync scraping page {page_num}: {e}")
                break

        return results

    def _scrape_demowebshop_sync(self, page, start_url: str, max_pages: int) -> List[Dict[str, Any]]:
        results = []
        current_url = start_url
        page_num = 1

        while current_url and page_num <= max_pages:
            logger.info(f"Playwright demowebshop: Scraping page {page_num}: {current_url}")
            try:
                page.goto(current_url, wait_until="domcontentloaded")
                
                items = page.locator(".product-item").all()
                if not items:
                    break

                page_data = []
                for item in items:
                    title_link = item.locator(".product-title a")
                    name = title_link.inner_text().strip()
                    product_url = urljoin(current_url, title_link.get_attribute("href"))
                    
                    price = "0.00"
                    price_elem = item.locator(".product-price, .actual-price").first
                    if price_elem.count() > 0:
                        price = price_elem.inner_text().strip()

                    page_data.append({
                        "name": name,
                        "price": price,
                        "product_url": product_url,
                        "rating": "0",
                        "category": "Products",
                        "description": "",
                        "image_url": "",
                        "scraper_type": "playwright"
                    })

                for item in page_data:
                    page.wait_for_timeout(int(self.delay * 1000))
                    try:
                        page.goto(item["product_url"], wait_until="domcontentloaded")
                        
                        # Category
                        breadcrumbs = page.locator(".breadcrumb a").all()
                        if breadcrumbs:
                            item["category"] = breadcrumbs[-1].inner_text().strip()
                            
                        # Description
                        desc_elem = page.locator(".full-description")
                        if desc_elem.count() > 0:
                            item["description"] = desc_elem.inner_text().strip()
                        else:
                            short_elem = page.locator(".short-description")
                            if short_elem.count() > 0:
                                item["description"] = short_elem.inner_text().strip()

                        # Image URL
                        img = page.locator(".gallery img").first
                        if img.count() > 0:
                            item["image_url"] = urljoin(item["product_url"], img.get_attribute("src"))

                        # Rating
                        rating_elem = page.locator(".rating div").first
                        if rating_elem.count() > 0:
                            style = rating_elem.get_attribute("style")
                            if style and "width:" in style:
                                width = style.replace("width:", "").replace("%", "").replace(";", "").strip()
                                item["rating"] = str(round(float(width) / 20.0, 1))

                        results.append(item)
                    except Exception as e:
                        logger.warning(f"Error fetching details: {e}")
                        results.append(item)

                if page_num < max_pages:
                    page.goto(current_url, wait_until="domcontentloaded")
                    next_button = page.locator("li.next-page a")
                    if next_button.count() > 0:
                        current_url = urljoin(current_url, next_button.get_attribute("href"))
                        page_num += 1
                    else:
                        break
                else:
                    break
            except Exception as e:
                logger.error(f"Error demowebshop sync scraping page {page_num}: {e}")
                break

        return results

    def _scrape_generic_sync(self, page, start_url: str, max_pages: int) -> List[Dict[str, Any]]:
        results = []
        current_url = start_url
        page_num = 1

        while current_url and page_num <= max_pages:
            logger.info(f"Playwright generic: Scraping page {page_num}: {current_url}")
            try:
                page.goto(current_url, wait_until="domcontentloaded")
                
                # Check for standard grid cards
                selectors = ["article", ".product-card", ".product-item", ".card", ".item-box"]
                cards = []
                for sel in selectors:
                    elems = page.locator(sel).all()
                    if len(elems) >= 3:
                        cards = elems
                        logger.info(f"Found cards using: {sel}")
                        break

                if not cards:
                    # anchors fallback
                    anchors = page.locator("a").all()
                    cards = [a for a in anchors if a.inner_text().strip()][:30]

                if not cards:
                    break

                for card in cards:
                    try:
                        # Name
                        name = ""
                        title_el = card.locator("h1, h2, h3, h4, .title, .name").first
                        if title_el.count() > 0:
                            name = title_el.inner_text().strip()
                        else:
                            name = card.inner_text().strip().split("\n")[0][:60]
                            
                        if not name or len(name) < 3:
                            continue

                        # Price
                        price = "$0.00"
                        price_el = card.locator(".price, .amount, [class*='price']").first
                        if price_el.count() > 0:
                            price = price_el.inner_text().strip()

                        # Image
                        image_url = ""
                        img_el = card.locator("img").first
                        if img_el.count() > 0:
                            image_url = urljoin(current_url, img_el.get_attribute("src") or "")

                        # Product Link
                        product_url = current_url
                        if card.get_attribute("href"):
                            product_url = urljoin(current_url, card.get_attribute("href"))
                        else:
                            link = card.locator("a").first
                            if link.count() > 0:
                                product_url = urljoin(current_url, link.get_attribute("href") or "")

                        results.append({
                            "name": name,
                            "price": price,
                            "product_url": product_url,
                            "rating": "3.0",
                            "category": "Generic",
                            "description": "Generic dynamically scraped details.",
                            "image_url": image_url,
                            "scraper_type": "playwright"
                        })
                    except Exception as e:
                        logger.warning(f"Error parsing generic: {e}")

                # Pagination
                next_btn = page.locator("//a[contains(translate(text(), 'NEXT', 'next'), 'next') or text()='>' or text()='»']").first
                if next_btn.count() > 0 and next_btn.is_visible():
                    href = next_btn.get_attribute("href")
                    if href:
                        current_url = urljoin(current_url, href)
                        page_num += 1
                    else:
                        next_btn.click()
                        page.wait_for_timeout(2000)
                        current_url = page.url
                        page_num += 1
                else:
                    break
            except Exception as e:
                logger.error(f"Error generic sync scraping page {page_num}: {e}")
                break

        return results

    # =====================================================================
    # ASYNCHRONOUS PLAYWRIGHT SCRAPING (BONUS FEATURE)
    # =====================================================================
    async def async_scrape(self, url: str, max_pages: int = 1) -> List[Dict[str, Any]]:
        """Asynchronous scraper workflow."""
        if not self.validate_url(url):
            logger.error(f"Invalid URL: {url}")
            return []

        logger.info(f"Starting Playwright (Async) scraping for {url}")
        results = []

        try:
            async with async_playwright() as p:
                browser_args = ["--no-sandbox", "--disable-setuid-sandbox"]
                
                proxy_server = self.get_random_proxy()
                proxy_config = None
                if proxy_server:
                    proxy_config = {"server": proxy_server}

                browser = await p.chromium.launch(headless=True, args=browser_args)
                
                context_args = {
                    "user_agent": self.get_user_agent(),
                    "ignore_https_errors": True
                }
                if proxy_config:
                    context_args["proxy"] = proxy_config

                context = await browser.new_context(**context_args)
                page = await context.new_page()

                # Enable route blocking for optimization
                await page.route("**/*.{css,png,jpg,jpeg,gif,svg,woff,woff2,ttf}", lambda route: route.abort() if "image" not in route.request.resource_type else route.continue_())

                domain = urlparse(url).netloc
                if "books.toscrape.com" in domain:
                    results = await self._scrape_books_async(page, url, max_pages)
                elif "demowebshop.tricentis.com" in domain:
                    results = await self._scrape_demowebshop_async(page, url, max_pages)
                else:
                    results = await self._scrape_generic_async(page, url, max_pages)

                await browser.close()
        except Exception as e:
            logger.error(f"Playwright Async Scraping failed: {e}")

        return results

    async def _scrape_books_async(self, page, start_url: str, max_pages: int) -> List[Dict[str, Any]]:
        results = []
        current_url = start_url
        page_num = 1

        while current_url and page_num <= max_pages:
            logger.info(f"Playwright Async books: Scraping page {page_num}")
            try:
                await page.goto(current_url, wait_until="domcontentloaded")
                
                pods = await page.locator("article.product_pod").all()
                if not pods:
                    break

                page_data = []
                for pod in pods:
                    title_link = pod.locator("h3 a")
                    title = await title_link.get_attribute("title")
                    href = await title_link.get_attribute("href")
                    product_url = urljoin(current_url, href)

                    price = (await pod.locator(".price_color").inner_text()).strip()
                    
                    rating_classes = (await pod.locator("p.star-rating").get_attribute("class")).split()
                    rating_star = "0"
                    for cls in rating_classes:
                        if cls.lower() != "star-rating":
                            rating_star = self.parse_rating_stars(cls)

                    image_src = await pod.locator("img").get_attribute("src")
                    image_url = urljoin(current_url, image_src)

                    page_data.append({
                        "name": title,
                        "price": price,
                        "rating": rating_star,
                        "product_url": product_url,
                        "image_url": image_url,
                        "category": "Books",
                        "scraper_type": "playwright_async"
                    })

                for item in page_data:
                    await page.wait_for_timeout(int(self.delay * 1000))
                    try:
                        await page.goto(item["product_url"], wait_until="domcontentloaded")
                        
                        breadcrumbs = await page.locator("ul.breadcrumb li").all()
                        if len(breadcrumbs) >= 3:
                            item["category"] = (await breadcrumbs[2].inner_text()).strip()

                        desc_header = page.locator("#product_description")
                        if await desc_header.count() > 0:
                            desc_p = page.locator("#product_description + p")
                            item["description"] = (await desc_p.inner_text()).strip()
                        else:
                            item["description"] = ""
                            
                        results.append(item)
                    except Exception as e:
                        logger.warning(f"Error fetching detail async: {e}")
                        item["description"] = ""
                        results.append(item)

                if page_num < max_pages:
                    await page.goto(current_url, wait_until="domcontentloaded")
                    next_button = page.locator("li.next a")
                    if await next_button.count() > 0:
                        current_url = urljoin(current_url, await next_button.get_attribute("href"))
                        page_num += 1
                    else:
                        break
                else:
                    break
            except Exception as e:
                logger.error(f"Error books async scraping: {e}")
                break

        return results

    async def _scrape_demowebshop_async(self, page, start_url: str, max_pages: int) -> List[Dict[str, Any]]:
        results = []
        current_url = start_url
        page_num = 1

        while current_url and page_num <= max_pages:
            logger.info(f"Playwright Async demowebshop: Scraping page {page_num}")
            try:
                await page.goto(current_url, wait_until="domcontentloaded")
                
                items = await page.locator(".product-item").all()
                if not items:
                    break

                page_data = []
                for item in items:
                    title_link = item.locator(".product-title a")
                    name = (await title_link.inner_text()).strip()
                    product_url = urljoin(current_url, await title_link.get_attribute("href"))
                    
                    price = "0.00"
                    price_elem = item.locator(".product-price, .actual-price").first
                    if await price_elem.count() > 0:
                        price = (await price_elem.inner_text()).strip()

                    page_data.append({
                        "name": name,
                        "price": price,
                        "product_url": product_url,
                        "rating": "0",
                        "category": "Products",
                        "description": "",
                        "image_url": "",
                        "scraper_type": "playwright_async"
                    })

                for item in page_data:
                    await page.wait_for_timeout(int(self.delay * 1000))
                    try:
                        await page.goto(item["product_url"], wait_until="domcontentloaded")
                        
                        breadcrumbs = await page.locator(".breadcrumb a").all()
                        if breadcrumbs:
                            item["category"] = (await breadcrumbs[-1].inner_text()).strip()
                            
                        desc_elem = page.locator(".full-description")
                        if await desc_elem.count() > 0:
                            item["description"] = (await desc_elem.inner_text()).strip()
                        else:
                            short_elem = page.locator(".short-description")
                            if await short_elem.count() > 0:
                                item["description"] = (await short_elem.inner_text()).strip()

                        img = page.locator(".gallery img").first
                        if await img.count() > 0:
                            item["image_url"] = urljoin(item["product_url"], await img.get_attribute("src"))

                        rating_elem = page.locator(".rating div").first
                        if await rating_elem.count() > 0:
                            style = await rating_elem.get_attribute("style")
                            if style and "width:" in style:
                                width = style.replace("width:", "").replace("%", "").replace(";", "").strip()
                                item["rating"] = str(round(float(width) / 20.0, 1))

                        results.append(item)
                    except Exception as e:
                        logger.warning(f"Error fetching detail async: {e}")
                        results.append(item)

                if page_num < max_pages:
                    await page.goto(current_url, wait_until="domcontentloaded")
                    next_button = page.locator("li.next-page a")
                    if await next_button.count() > 0:
                        current_url = urljoin(current_url, await next_button.get_attribute("href"))
                        page_num += 1
                    else:
                        break
                else:
                    break
            except Exception as e:
                logger.error(f"Error demowebshop async scraping: {e}")
                break

        return results

    async def _scrape_generic_async(self, page, start_url: str, max_pages: int) -> List[Dict[str, Any]]:
        results = []
        current_url = start_url
        page_num = 1

        while current_url and page_num <= max_pages:
            logger.info(f"Playwright Async generic: Scraping page {page_num}")
            try:
                await page.goto(current_url, wait_until="domcontentloaded")
                
                selectors = ["article", ".product-card", ".product-item", ".card", ".item-box"]
                cards = []
                for sel in selectors:
                    elems = await page.locator(sel).all()
                    if len(elems) >= 3:
                        cards = elems
                        break

                if not cards:
                    anchors = await page.locator("a").all()
                    cards = [a for a in anchors if (await a.inner_text()).strip()][:30]

                if not cards:
                    break

                for card in cards:
                    try:
                        name = ""
                        title_el = card.locator("h1, h2, h3, h4, .title, .name").first
                        if await title_el.count() > 0:
                            name = (await title_el.inner_text()).strip()
                        else:
                            name = (await card.inner_text()).strip().split("\n")[0][:60]
                            
                        if not name or len(name) < 3:
                            continue

                        price = "$0.00"
                        price_el = card.locator(".price, .amount, [class*='price']").first
                        if await price_el.count() > 0:
                            price = (await price_el.inner_text()).strip()

                        image_url = ""
                        img_el = card.locator("img").first
                        if await img_el.count() > 0:
                            image_url = urljoin(current_url, await img_el.get_attribute("src") or "")

                        product_url = current_url
                        if await card.get_attribute("href"):
                            product_url = urljoin(current_url, await card.get_attribute("href"))
                        else:
                            link = card.locator("a").first
                            if await link.count() > 0:
                                product_url = urljoin(current_url, await link.get_attribute("href") or "")

                        results.append({
                            "name": name,
                            "price": price,
                            "product_url": product_url,
                            "rating": "3.0",
                            "category": "Generic",
                            "description": "Generic dynamically scraped details.",
                            "image_url": image_url,
                            "scraper_type": "playwright_async"
                        })
                    except Exception as e:
                        logger.warning(f"Error parsing generic: {e}")

                next_btn = page.locator("//a[contains(translate(text(), 'NEXT', 'next'), 'next') or text()='>' or text()='»']").first
                if await next_btn.count() > 0 and await next_btn.is_visible():
                    href = await next_btn.get_attribute("href")
                    if href:
                        current_url = urljoin(current_url, href)
                        page_num += 1
                    else:
                        await next_btn.click()
                        await page.wait_for_timeout(2000)
                        current_url = page.url
                        page_num += 1
                else:
                    break
            except Exception as e:
                logger.error(f"Error generic async scraping: {e}")
                break

        return results
