import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scrapers.base_scraper import BaseScraper
from scrapers.bs4_scraper import BS4Scraper

class TestBaseScraper:
    def setup_method(self):
        self.scraper = BaseScraper(delay=0.1, retries=1)

    def test_validate_url(self):
        assert self.scraper.validate_url("https://books.toscrape.com/")
        assert not self.scraper.validate_url("")
        assert not self.scraper.validate_url("not-a-url")

    def test_get_user_agent(self):
        ua = self.scraper.get_user_agent()
        assert len(ua) > 10

    def test_parse_rating_stars(self):
        assert self.scraper.parse_rating_stars("Three") == "3"
        assert self.scraper.parse_rating_stars("Five") == "5"
        assert self.scraper.parse_rating_stars("One") == "1"
        assert self.scraper.parse_rating_stars("invalid") == "0"

    def test_get_proxy_dict(self):
        proxy_dict = self.scraper.get_proxy_dict()
        assert proxy_dict is None

class TestBS4Scraper:
    def setup_method(self):
        self.scraper = BS4Scraper(delay=0.1, retries=1)

    def test_scrape_invalid_url(self):
        results = self.scraper.scrape("")
        assert results == []

    @pytest.mark.network
    def test_scrape_books_toscrape(self):
        results = self.scraper.scrape("https://books.toscrape.com/", max_pages=1)
        assert len(results) > 0
        assert results[0].get("name")
        assert results[0].get("price")
        assert results[0].get("scraper_type") == "bs4"

    @pytest.mark.network
    def test_scrape_demowebshop(self):
        results = self.scraper.scrape("https://demowebshop.tricentis.com/", max_pages=1)
        assert len(results) > 0
