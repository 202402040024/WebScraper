import logging
import json
import os
import subprocess
import tempfile
import sys
from urllib.parse import urlparse
from typing import Dict, List, Any, Optional
from .base_scraper import BaseScraper

logger = logging.getLogger("scraper_dashboard.scrapy_scraper")

class ScrapyScraper(BaseScraper):
    """
    Scrapy scraper. Executes a Scrapy Spider in a subprocess to avoid
    Twisted Reactor conflicts in Streamlit threads.
    """

    def scrape(self, url: str, max_pages: int = 1) -> List[Dict[str, Any]]:
        if not self.validate_url(url):
            logger.error(f"Invalid URL: {url}")
            return []

        logger.info(f"Starting Scrapy scraping for {url} with max pages: {max_pages}")
        
        # Temp files for spider script and output data
        fd_script, script_path = tempfile.mkstemp(suffix=".py")
        fd_output, output_path = tempfile.mkstemp(suffix=".json")
        
        # Close the file descriptors as subprocess will open them
        os.close(fd_script)
        os.close(fd_output)

        domain = urlparse(url).netloc
        user_agent = self.get_user_agent()
        proxy = self.get_random_proxy()

        # Generate Scrapy Spider source code
        spider_code = self._generate_spider_code(url, domain, max_pages, user_agent, proxy, output_path)

        results = []
        try:
            # Write spider script
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(spider_code)

            # Run spider script via python subprocess
            env = os.environ.copy()
            # Set PYTHONPATH to include current dir so imports are resolved
            env["PYTHONPATH"] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

            logger.info("Launching Scrapy subprocess...")
            process = subprocess.run(
                [sys.executable, script_path],
                env=env,
                capture_output=True,
                text=True,
                timeout=180
            )

            if process.returncode != 0:
                logger.error(f"Scrapy subprocess failed with return code {process.returncode}")
                logger.error(f"Subprocess stderr: {process.stderr}")
            else:
                logger.info("Scrapy subprocess finished successfully.")

            # Load results
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                with open(output_path, "r", encoding="utf-8") as f:
                    results = json.load(f)
                logger.info(f"Loaded {len(results)} items from Scrapy output.")
            else:
                logger.warning("Scrapy output file was empty or not found.")

        except Exception as e:
            logger.error(f"Error executing Scrapy subprocess: {e}")
        finally:
            # Clean up temp files
            for path in [script_path, output_path]:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except Exception as e:
                    logger.warning(f"Failed to remove temp file {path}: {e}")

        return results

    def _generate_spider_code(
        self,
        start_url: str,
        domain: str,
        max_pages: int,
        user_agent: str,
        proxy: Optional[str],
        output_path: str
    ) -> str:
        """Generates the python code for the Scrapy Spider that will run in the subprocess."""
        proxy_setting = f"'{proxy}'" if proxy else "None"
        # Escape backslashes in path for safe injection into generated Python source
        safe_output_path = output_path.replace("\\", "\\\\")
        
        return f"""
import json
import scrapy
from scrapy.crawler import CrawlerProcess
from urllib.parse import urljoin

class DashboardSpider(scrapy.Spider):
    name = 'dashboard_spider'
    start_urls = ['{start_url}']
    
    custom_settings = {{
        'USER_AGENT': '{user_agent}',
        'ROBOTSTXT_OBEY': False,
        'LOG_LEVEL': 'WARNING',
        'HTTPPROXY_ENABLED': {str(proxy is not None)},
        'CONCURRENT_REQUESTS': 8,
        'DOWNLOAD_TIMEOUT': 30,
    }}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.results = []
        self.pages_scraped = 0
        self.max_pages = {max_pages}
        self.proxy = {proxy_setting}

    def start_requests(self):
        for url in self.start_urls:
            meta = {{}}
            if self.proxy:
                meta['proxy'] = self.proxy
            yield scrapy.Request(url, self.parse, meta=meta)

    def parse(self, response):
        self.pages_scraped += 1
        self.logger.info(f"Scrapy: Parsing page {{self.pages_scraped}}: {{response.url}}")

        domain = '{domain}'
        if 'books.toscrape.com' in domain:
            yield from self.parse_books(response)
        elif 'demowebshop.tricentis.com' in domain:
            yield from self.parse_demowebshop(response)
        else:
            yield from self.parse_generic(response)

    # =====================================================================
    # BOOKS TO SCRAPE SPECIALIZED PARSER
    # =====================================================================
    def parse_books(self, response):
        pods = response.css('article.product_pod')
        for pod in pods:
            href = pod.css('h3 a::attr(href)').get()
            product_url = urljoin(response.url, href)
            
            title = pod.css('h3 a::attr(title)').get()
            price = pod.css('.price_color::text').get()
            
            # Star rating class mapping
            rating_class = pod.css('p.star-rating::attr(class)').get()
            rating_classes = rating_class.split() if rating_class else []
            rating_star = '0'
            word_map = {{'one': '1', 'two': '2', 'three': '3', 'four': '4', 'five': '5'}}
            for cls in rating_classes:
                if cls.lower() != 'star-rating' and cls.lower() in word_map:
                    rating_star = word_map[cls.lower()]

            image_src = pod.css('img::attr(src)').get()
            image_url = urljoin(response.url, image_src)

            # Create request to scrape book detail page for description & category
            item = {{
                'name': title,
                'price': price,
                'rating': rating_star,
                'product_url': product_url,
                'image_url': image_url,
                'category': 'Books',
                'description': '',
                'scraper_type': 'scrapy'
            }}
            
            meta = {{'item': item}}
            if self.proxy:
                meta['proxy'] = self.proxy
                
            yield scrapy.Request(product_url, self.parse_book_details, meta=meta)

        # Pagination
        if self.pages_scraped < self.max_pages:
            next_href = response.css('li.next a::attr(href)').get()
            if next_href:
                next_url = urljoin(response.url, next_href)
                meta = {{}}
                if self.proxy:
                    meta['proxy'] = self.proxy
                yield scrapy.Request(next_url, self.parse, meta=meta)

    def parse_book_details(self, response):
        item = response.meta['item']
        
        # Category
        breadcrumbs = response.css('ul.breadcrumb li a::text').getall()
        if len(breadcrumbs) >= 3:
            item['category'] = breadcrumbs[2].strip()
            
        # Description
        desc = response.css('#product_description + p::text').get()
        if desc:
            item['description'] = desc.strip()
            
        self.results.append(item)
        yield item

    # =====================================================================
    # DEMO WEBSHOP SPECIALIZED PARSER
    # =====================================================================
    def parse_demowebshop(self, response):
        items = response.css('.product-item')
        for item_box in items:
            title_link = item_box.css('.product-title a')
            name = title_link.css('::text').get().strip()
            href = title_link.css('::attr(href)').get()
            product_url = urljoin(response.url, href)

            price = '0.00'
            price_tag = item_box.css('.product-price::text, .actual-price::text').get()
            if price_tag:
                price = price_tag.strip()

            item = {{
                'name': name,
                'price': price,
                'product_url': product_url,
                'rating': '0',
                'category': 'Products',
                'description': '',
                'image_url': '',
                'scraper_type': 'scrapy'
            }}
            
            meta = {{'item': item}}
            if self.proxy:
                meta['proxy'] = self.proxy
                
            yield scrapy.Request(product_url, self.parse_demowebshop_details, meta=meta)

        # Pagination
        if self.pages_scraped < self.max_pages:
            next_href = response.css('li.next-page a::attr(href)').get()
            if next_href:
                next_url = urljoin(response.url, next_href)
                meta = {{}}
                if self.proxy:
                    meta['proxy'] = self.proxy
                yield scrapy.Request(next_url, self.parse, meta=meta)

    def parse_demowebshop_details(self, response):
        item = response.meta['item']
        
        # Category
        breadcrumbs = response.css('.breadcrumb a::text').getall()
        if breadcrumbs:
            item['category'] = breadcrumbs[-1].strip()
            
        # Description
        desc = response.css('.full-description::text').get()
        if not desc:
            desc = response.css('.short-description::text').get()
        if desc:
            item['description'] = desc.strip()
            
        # Image
        img_src = response.css('.gallery img::attr(src)').get()
        if img_src:
            item['image_url'] = urljoin(response.url, img_src)

        # Rating style logic
        rating_style = response.css('.rating div::attr(style)').get()
        if rating_style and 'width:' in rating_style:
            width = rating_style.replace('width:', '').replace('%', '').replace(';', '').strip()
            try:
                item['rating'] = str(round(float(width) / 20.0, 1))
            except ValueError:
                pass

        self.results.append(item)
        yield item

    # =====================================================================
    # GENERIC PARSER
    # =====================================================================
    def parse_generic(self, response):
        # Fallback card selectors
        cards = response.css('article, .product-card, .product-item, .card, .item-box')
        if not cards:
            # Fallback anchors with text
            cards = response.css('a')

        for card in cards:
            name = card.css('h1::text, h2::text, h3::text, h4::text, .title::text, .name::text, a::text').get()
            if not name:
                continue
            name = name.strip()
            if len(name) < 3:
                continue

            price = card.css('.price::text, .amount::text, [class*="price"]::text').get() or '$0.00'
            
            href = card.css('a::attr(href)').get() or card.css('::attr(href)').get()
            product_url = urljoin(response.url, href) if href else response.url
            
            img_src = card.css('img::attr(src)').get()
            image_url = urljoin(response.url, img_src) if img_src else ''

            item = {{
                'name': name[:60],
                'price': price.strip(),
                'rating': '3.0',
                'product_url': product_url,
                'image_url': image_url,
                'category': 'Generic',
                'description': 'Generic scraped product details.',
                'scraper_type': 'scrapy'
            }}
            self.results.append(item)
            yield item

    def closed(self, reason):
        # Save results to the output file on closing
        with open('{safe_output_path}', 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=4, ensure_ascii=False)

if __name__ == '__main__':
    process = CrawlerProcess()
    process.crawl(DashboardSpider)
    process.start()
"""
