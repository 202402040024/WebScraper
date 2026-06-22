import logging
import os
import shutil
import time
from urllib.parse import urljoin, urlparse
from typing import Dict, List, Any, Optional
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from .base_scraper import BaseScraper

logger = logging.getLogger("scraper_dashboard.selenium_scraper")


def _find_chromedriver() -> Optional[str]:
    """
    Find chromedriver from system PATH first (Render/Linux),
    then try webdriver_manager cache (Windows/local dev).
    """
    # 1. System chromedriver (installed via apt on Render)
    system = shutil.which("chromedriver")
    if system:
        logger.info(f"Using system chromedriver: {system}")
        return system

    # 2. webdriver_manager cache (local dev — never triggers a download)
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        path = ChromeDriverManager().install()
        logger.info(f"Using cached chromedriver: {path}")
        return path
    except Exception as e:
        logger.warning(f"webdriver_manager failed: {e}")

    return None


def _find_chrome_binary() -> Optional[str]:
    """Find Chrome/Chromium binary for Selenium on Linux/Render."""
    for candidate in [
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
    ]:
        if os.path.exists(candidate):
            return candidate
    return shutil.which("chromium") or shutil.which("chromium-browser")


def _build_driver() -> webdriver.Chrome:
    """Build a headless Chrome driver, trying system chromedriver then webdriver_manager."""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-extensions")
    options.add_argument("--window-size=1280,800")
    options.add_experimental_option("excludeSwitches", ["enable-logging"])

    # Use system Chrome/Chromium binary if available (Render/Linux)
    chrome_bin = _find_chrome_binary()
    if chrome_bin:
        options.binary_location = chrome_bin

    driver_path = _find_chromedriver()
    if driver_path:
        service = Service(executable_path=driver_path)
        driver = webdriver.Chrome(service=service, options=options)
    else:
        driver = webdriver.Chrome(options=options)

    driver.set_page_load_timeout(30)
    return driver


class SeleniumScraper(BaseScraper):
    """Scraper using Selenium headless Chrome."""

    def scrape(self, url: str, max_pages: int = 1) -> List[Dict[str, Any]]:
        if not self.validate_url(url):
            logger.error(f"Invalid URL: {url}")
            return []

        logger.info(f"Starting Selenium scraping for {url}")
        driver = None
        results = []
        try:
            driver = _build_driver()
            driver.execute_cdp_cmd(
                "Network.setUserAgentOverride",
                {"userAgent": self.get_user_agent()}
            )
            domain = urlparse(url).netloc
            if "books.toscrape.com" in domain:
                results = self._scrape_books(driver, url, max_pages)
            elif "demowebshop.tricentis.com" in domain:
                results = self._scrape_demowebshop(driver, url, max_pages)
            else:
                results = self._scrape_generic(driver, url, max_pages)
        except Exception as e:
            logger.error(f"Selenium execution error: {e}")
            raise
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
        return results

    # =========================================================
    # BOOKS.TOSCRAPE.COM
    # =========================================================
    def _scrape_books(self, driver, start_url: str, max_pages: int) -> List[Dict[str, Any]]:
        results = []
        current_url = start_url
        page_num = 1

        while current_url and page_num <= max_pages:
            logger.info(f"Selenium books page {page_num}: {current_url}")
            driver.get(current_url)
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "article.product_pod"))
                )
            except Exception:
                logger.warning("Timeout waiting for products")
                break

            pods = driver.find_elements(By.CSS_SELECTOR, "article.product_pod")
            page_data = []
            for pod in pods:
                try:
                    a = pod.find_element(By.CSS_SELECTOR, "h3 a")
                    title = a.get_attribute("title")
                    href = a.get_attribute("href")
                    price = pod.find_element(By.CSS_SELECTOR, ".price_color").text.strip()
                    rating_cls = pod.find_element(By.CSS_SELECTOR, "p.star-rating").get_attribute("class").split()
                    rating = next((self.parse_rating_stars(c) for c in rating_cls if c.lower() != "star-rating"), "0")
                    img_src = pod.find_element(By.CSS_SELECTOR, "img").get_attribute("src")
                    page_data.append({
                        "name": title, "price": price, "rating": rating,
                        "product_url": href, "image_url": img_src,
                        "category": "Books", "description": "",
                        "scraper_type": "selenium"
                    })
                except Exception as e:
                    logger.warning(f"Error parsing pod: {e}")

            for item in page_data:
                time.sleep(self.delay)
                try:
                    driver.get(item["product_url"])
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "ul.breadcrumb"))
                    )
                    crumbs = driver.find_elements(By.CSS_SELECTOR, "ul.breadcrumb li")
                    if len(crumbs) >= 3:
                        item["category"] = crumbs[2].text.strip()
                    try:
                        desc_h = driver.find_element(By.ID, "product_description")
                        item["description"] = desc_h.find_element(By.XPATH, "following-sibling::p").text.strip()
                    except Exception:
                        item["description"] = ""
                except Exception as e:
                    logger.warning(f"Detail fetch failed: {e}")
                    item["description"] = ""
                results.append(item)

            # Pagination
            if page_num < max_pages:
                driver.get(current_url)
                nxt = driver.find_elements(By.CSS_SELECTOR, "li.next a")
                if nxt:
                    current_url = nxt[0].get_attribute("href")
                    page_num += 1
                else:
                    break
            else:
                break

        return results

    # =========================================================
    # DEMOWEBSHOP
    # =========================================================
    def _scrape_demowebshop(self, driver, start_url: str, max_pages: int) -> List[Dict[str, Any]]:
        results = []
        current_url = start_url
        page_num = 1

        while current_url and page_num <= max_pages:
            logger.info(f"Selenium demowebshop page {page_num}")
            driver.get(current_url)
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".product-item"))
                )
            except Exception:
                break

            page_data = []
            for box in driver.find_elements(By.CSS_SELECTOR, ".product-item"):
                try:
                    a = box.find_element(By.CSS_SELECTOR, ".product-title a")
                    name = a.text.strip()
                    product_url = a.get_attribute("href")
                    price = "0.00"
                    try:
                        price = box.find_element(By.CSS_SELECTOR, ".product-price, .actual-price").text.strip()
                    except Exception:
                        pass
                    page_data.append({
                        "name": name, "price": price, "product_url": product_url,
                        "rating": "0", "category": "Products", "description": "",
                        "image_url": "", "scraper_type": "selenium"
                    })
                except Exception as e:
                    logger.warning(f"Error parsing item: {e}")

            for item in page_data:
                time.sleep(self.delay)
                try:
                    driver.get(item["product_url"])
                    crumbs = driver.find_elements(By.CSS_SELECTOR, ".breadcrumb a")
                    if crumbs:
                        item["category"] = crumbs[-1].text.strip()
                    for sel in [".full-description", ".short-description"]:
                        try:
                            item["description"] = driver.find_element(By.CSS_SELECTOR, sel).text.strip()
                            break
                        except Exception:
                            pass
                    try:
                        item["image_url"] = driver.find_element(By.CSS_SELECTOR, ".gallery img").get_attribute("src")
                    except Exception:
                        pass
                    try:
                        style = driver.find_element(By.CSS_SELECTOR, ".rating div").get_attribute("style")
                        if style and "width:" in style:
                            w = style.replace("width:", "").replace("%", "").replace(";", "").strip()
                            item["rating"] = str(round(float(w) / 20.0, 1))
                    except Exception:
                        pass
                except Exception as e:
                    logger.warning(f"Detail error: {e}")
                results.append(item)

            if page_num < max_pages:
                driver.get(current_url)
                nxt = driver.find_elements(By.CSS_SELECTOR, "li.next-page a")
                if nxt:
                    current_url = nxt[0].get_attribute("href")
                    page_num += 1
                else:
                    break
            else:
                break

        return results

    # =========================================================
    # GENERIC
    # =========================================================
    def _scrape_generic(self, driver, start_url: str, max_pages: int) -> List[Dict[str, Any]]:
        results = []
        current_url = start_url
        page_num = 1

        while current_url and page_num <= max_pages:
            driver.get(current_url)
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

            cards = []
            for sel in ["article", ".product-card", ".product-item", ".card", ".item-box"]:
                cards = driver.find_elements(By.CSS_SELECTOR, sel)
                if len(cards) >= 3:
                    break
            if not cards:
                cards = [c for c in driver.find_elements(By.TAG_NAME, "a") if c.text.strip()][:30]
            if not cards:
                break

            for card in cards:
                try:
                    name = ""
                    try:
                        name = card.find_element(By.CSS_SELECTOR, "h1,h2,h3,h4,.title,.name").text.strip()
                    except Exception:
                        name = card.text.strip().split("\n")[0][:60]
                    if not name or len(name) < 3:
                        continue
                    price = "$0.00"
                    try:
                        price = card.find_element(By.CSS_SELECTOR, ".price,.amount,[class*='price']").text.strip()
                    except Exception:
                        pass
                    image_url = ""
                    try:
                        image_url = card.find_element(By.TAG_NAME, "img").get_attribute("src") or ""
                    except Exception:
                        pass
                    product_url = current_url
                    try:
                        product_url = (card if card.tag_name == "a" else card.find_element(By.TAG_NAME, "a")).get_attribute("href") or current_url
                    except Exception:
                        pass
                    results.append({
                        "name": name, "price": price, "product_url": product_url,
                        "rating": "3.0", "category": "Generic",
                        "description": "Generic scraped item.",
                        "image_url": image_url, "scraper_type": "selenium"
                    })
                except Exception as e:
                    logger.warning(f"Generic parse error: {e}")

            try:
                nxt = driver.find_elements(By.XPATH, "//a[contains(translate(text(),'NEXT','next'),'next') or text()='>' or text()='»']")
                if nxt:
                    href = nxt[0].get_attribute("href")
                    if href and href != current_url:
                        current_url = href
                        page_num += 1
                    else:
                        break
                else:
                    break
            except Exception:
                break

        return results
