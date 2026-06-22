import logging
import time
from urllib.parse import urljoin, urlparse
from typing import Dict, List, Any, Optional
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from .base_scraper import BaseScraper

logger = logging.getLogger("scraper_dashboard.selenium_scraper")

class SeleniumScraper(BaseScraper):
    """
    Scraper using Selenium. Perfect for dynamically loaded JavaScript/AJAX sites.
    Runs headless Chrome.
    """

    def _setup_driver(self) -> webdriver.Chrome:
        """Configures and returns a headless Chrome Webdriver instance."""
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument(f"--user-agent={self.get_user_agent()}")

        # Add proxy if available
        proxy = self.get_random_proxy()
        if proxy:
            options.add_argument(f"--proxy-server={proxy}")

        # Suppress logging noise
        options.add_experimental_option('excludeSwitches', ['enable-logging'])

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(30)
        return driver

    def scrape(self, url: str, max_pages: int = 1) -> List[Dict[str, Any]]:
        if not self.validate_url(url):
            logger.error(f"Invalid URL: {url}")
            return []

        logger.info(f"Starting Selenium scraping for {url}")
        driver = None
        results = []
        try:
            driver = self._setup_driver()
            domain = urlparse(url).netloc

            if "books.toscrape.com" in domain:
                results = self._scrape_books(driver, url, max_pages)
            elif "demowebshop.tricentis.com" in domain:
                results = self._scrape_demowebshop(driver, url, max_pages)
            else:
                results = self._scrape_generic(driver, url, max_pages)

        except Exception as e:
            logger.error(f"Selenium execution error: {e}")
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception as e:
                    logger.warning(f"Error quitting driver: {e}")

        return results

    # =====================================================================
    # BOOKS TO SCRAPE SPECIALIZED SCRAPER
    # =====================================================================
    def _scrape_books(self, driver: webdriver.Chrome, start_url: str, max_pages: int) -> List[Dict[str, Any]]:
        results = []
        driver.get(start_url)
        page_num = 1

        while page_num <= max_pages:
            logger.info(f"Selenium books.toscrape: Scraping page {page_num}")
            
            # Wait for product containers to load
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, "article.product_pod"))
                )
            except Exception:
                logger.warning(f"No products found on page {page_num} within timeout.")
                break

            pods = driver.find_elements(By.CSS_SELECTOR, "article.product_pod")
            if not pods:
                break

            # Collect basic page details
            page_data = []
            for pod in pods:
                try:
                    title_elem = pod.find_element(By.CSS_SELECTOR, "h3 a")
                    title = title_elem.get_attribute("title")
                    href = title_elem.get_attribute("href")
                    
                    price = pod.find_element(By.CSS_SELECTOR, ".price_color").text.strip()
                    
                    rating_elem = pod.find_element(By.CSS_SELECTOR, "p.star-rating")
                    rating_classes = rating_elem.get_attribute("class").split()
                    rating_star = "0"
                    for cls in rating_classes:
                        if cls.lower() != "star-rating":
                            rating_star = self.parse_rating_stars(cls)

                    img_elem = pod.find_element(By.CSS_SELECTOR, "img")
                    image_url = img_elem.get_attribute("src")

                    page_data.append({
                        "name": title,
                        "price": price,
                        "rating": rating_star,
                        "product_url": href,
                        "image_url": image_url,
                        "category": "Books",
                        "scraper_type": "selenium"
                    })
                except Exception as e:
                    logger.warning(f"Error parsing pod in Selenium: {e}")

            # Now visit each product link to get description & category
            for item in page_data:
                time.sleep(self.delay) # Politeness
                try:
                    driver.get(item["product_url"])
                    
                    # Category breadcrumbs
                    try:
                        breadcrumbs = driver.find_elements(By.CSS_SELECTOR, "ul.breadcrumb li")
                        if len(breadcrumbs) >= 3:
                            item["category"] = breadcrumbs[2].text.strip()
                    except Exception:
                        pass

                    # Description
                    try:
                        desc_header = driver.find_element(By.ID, "product_description")
                        desc_p = desc_header.find_element(By.XPATH, "following-sibling::p")
                        item["description"] = desc_p.text.strip()
                    except Exception:
                        item["description"] = ""

                    results.append(item)
                except Exception as e:
                    logger.warning(f"Error fetching detail for {item['product_url']}: {e}")
                    # Still save the partial item
                    item["description"] = ""
                    results.append(item)

            # Return to list URL or pagination click
            if page_num < max_pages:
                try:
                    # Navigate back to category listing
                    # Or check for next button
                    driver.get(start_url) # go back to get page list
                    # Wait for products
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_all_elements_located((By.CSS_SELECTOR, "article.product_pod"))
                    )
                    
                    # We need to find the correct next button for page N
                    # Better yet, books.toscrape URL structure is predictable:
                    # page 1 is e.g. /page-1.html or similar. Let's click 'next' button
                    next_btns = driver.find_elements(By.CSS_SELECTOR, "li.next a")
                    if next_btns:
                        next_url = next_btns[0].get_attribute("href")
                        start_url = next_url
                        driver.get(start_url)
                        page_num += 1
                    else:
                        break
                except Exception as e:
                    logger.warning(f"Pagination click failed: {e}")
                    break
            else:
                break

        return results

    # =====================================================================
    # DEMO WEBSHOP SPECIALIZED SCRAPER
    # =====================================================================
    def _scrape_demowebshop(self, driver: webdriver.Chrome, start_url: str, max_pages: int) -> List[Dict[str, Any]]:
        results = []
        driver.get(start_url)
        page_num = 1

        while page_num <= max_pages:
            logger.info(f"Selenium demowebshop: Scraping page {page_num}")
            
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "product-item"))
                )
            except Exception:
                logger.warning(f"No products found on Demo Web Shop page {page_num}")
                break

            items = driver.find_elements(By.CLASS_NAME, "product-item")
            if not items:
                break

            page_data = []
            for item in items:
                try:
                    title_elem = item.find_element(By.CSS_SELECTOR, ".product-title a")
                    name = title_elem.text.strip()
                    product_url = title_elem.get_attribute("href")
                    
                    price = "0.00"
                    try:
                        price_elem = item.find_element(By.CSS_SELECTOR, ".product-price, .actual-price")
                        price = price_elem.text.strip()
                    except Exception:
                        pass

                    page_data.append({
                        "name": name,
                        "price": price,
                        "product_url": product_url,
                        "rating": "0",
                        "category": "Products",
                        "description": "",
                        "image_url": "",
                        "scraper_type": "selenium"
                    })
                except Exception as e:
                    logger.warning(f"Error parsing item: {e}")

            # Fetch details
            for item in page_data:
                time.sleep(self.delay)
                try:
                    driver.get(item["product_url"])
                    
                    # Category breadcrumbs
                    try:
                        breadcrumbs = driver.find_elements(By.CSS_SELECTOR, ".breadcrumb a")
                        if breadcrumbs:
                            item["category"] = breadcrumbs[-1].text.strip()
                    except Exception:
                        pass
                    
                    # Description
                    try:
                        desc_elem = driver.find_element(By.CLASS_NAME, "full-description")
                        item["description"] = desc_elem.text.strip()
                    except Exception:
                        try:
                            desc_elem = driver.find_element(By.CLASS_NAME, "short-description")
                            item["description"] = desc_elem.text.strip()
                        except Exception:
                            item["description"] = ""
                            
                    # Image URL
                    try:
                        img_elem = driver.find_element(By.CSS_SELECTOR, ".gallery img")
                        item["image_url"] = img_elem.get_attribute("src")
                    except Exception:
                        pass

                    # Rating
                    try:
                        rating_elem = driver.find_element(By.CSS_SELECTOR, ".rating div")
                        style = rating_elem.get_attribute("style")
                        if style and "width:" in style:
                            width = style.replace("width:", "").replace("%", "").replace(";", "").strip()
                            item["rating"] = str(round(float(width) / 20.0, 1))
                    except Exception:
                        pass

                    results.append(item)
                except Exception as e:
                    logger.warning(f"Error getting details for {item['product_url']}: {e}")
                    results.append(item)

            if page_num < max_pages:
                try:
                    # Navigate back or click next
                    driver.get(start_url)
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CLASS_NAME, "product-item"))
                    )
                    next_btns = driver.find_elements(By.CSS_SELECTOR, "li.next-page a")
                    if next_btns:
                        next_url = next_btns[0].get_attribute("href")
                        start_url = next_url
                        driver.get(start_url)
                        page_num += 1
                    else:
                        break
                except Exception as e:
                    logger.warning(f"Error paginating demowebshop: {e}")
                    break
            else:
                break

        return results

    # =====================================================================
    # GENERIC HEURISTIC SCRAPER
    # =====================================================================
    def _scrape_generic(self, driver: webdriver.Chrome, start_url: str, max_pages: int) -> List[Dict[str, Any]]:
        results = []
        driver.get(start_url)
        page_num = 1

        while page_num <= max_pages:
            logger.info(f"Selenium generic: Scraping page {page_num}")
            
            # Simple wait for DOM body
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
            except Exception:
                break

            # Find links or items that might look like products
            # We look for card containers first
            card_selectors = [
                "article", ".product-card", ".product-item", ".card", ".item-box", "[class*='product']"
            ]
            
            cards = []
            for sel in card_selectors:
                cards = driver.find_elements(By.CSS_SELECTOR, sel)
                if len(cards) >= 3:
                    logger.info(f"Found cards using selector: {sel}")
                    break
                    
            if not cards:
                # Fallback to anchors
                cards = driver.find_elements(By.TAG_NAME, "a")
                cards = [c for c in cards if c.text.strip()][:30]

            if not cards:
                break

            for card in cards:
                try:
                    # Extract name
                    name = ""
                    try:
                        header = card.find_element(By.CSS_SELECTOR, "h1, h2, h3, h4, .title, .name")
                        name = header.text.strip()
                    except Exception:
                        name = card.text.strip().split("\n")[0][:60]

                    if not name or len(name) < 3:
                        continue

                    # Extract price
                    price = "$0.00"
                    try:
                        price_elem = card.find_element(By.CSS_SELECTOR, ".price, .amount, [class*='price']")
                        price = price_elem.text.strip()
                    except Exception:
                        pass

                    # Extract image
                    image_url = ""
                    try:
                        img = card.find_element(By.TAG_NAME, "img")
                        image_url = img.get_attribute("src")
                    except Exception:
                        pass

                    # Extract link
                    product_url = start_url
                    try:
                        if card.tag_name == "a":
                            product_url = card.get_attribute("href")
                        else:
                            link = card.find_element(By.TAG_NAME, "a")
                            product_url = link.get_attribute("href")
                    except Exception:
                        pass

                    results.append({
                        "name": name,
                        "price": price,
                        "product_url": product_url,
                        "rating": "3.0",
                        "category": "Generic",
                        "description": "Generic dynamically scraped product details.",
                        "image_url": image_url,
                        "scraper_type": "selenium"
                    })
                except Exception as e:
                    logger.warning(f"Error parsing generic item: {e}")

            # Try to paginate using text matches
            try:
                next_btns = driver.find_elements(By.XPATH, "//a[contains(translate(text(), 'NEXT', 'next'), 'next') or text()='>' or text()='»']")
                if next_btns:
                    next_url = next_btns[0].get_attribute("href")
                    if next_url and next_url != driver.current_url:
                        start_url = next_url
                        driver.get(start_url)
                        page_num += 1
                    else:
                        # try click
                        next_btns[0].click()
                        time.sleep(2)
                        page_num += 1
                else:
                    break
            except Exception:
                break

        return results
