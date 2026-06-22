import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.mongodb import MongoDBManager, clean_price, clean_rating

@pytest.fixture
def db():
    mgr = MongoDBManager()
    yield mgr
    if mgr.is_connected:
        mgr.products.delete_many({})
        mgr.logs.delete_many({})

def test_clean_price():
    assert clean_price("$19.99") == 19.99
    assert clean_price("£51.77") == 51.77
    assert clean_price("100") == 100.0
    assert clean_price(42.5) == 42.5
    assert clean_price("") == 0.0
    assert clean_price(None) == 0.0

def test_clean_rating():
    assert clean_rating("Three") == 3.0
    assert clean_rating("five") == 5.0
    assert clean_rating(4) == 4.0
    assert clean_rating("80%") == 80.0
    assert clean_rating("") == 0.0

def test_mongo_connection(db):
    assert hasattr(db, "is_connected")

def test_insert_and_query(db):
    if not db.is_connected:
        pytest.skip("MongoDB not available")
    product = {
        "name": "Test Product",
        "price": "$29.99",
        "rating": "Four",
        "category": "Tests",
        "product_url": "http://test.com/product1",
        "image_url": "http://test.com/img.jpg",
        "scraper_type": "test"
    }
    success, msg = db.insert_product(product)
    assert success
    results = db.get_products(search_query="Test")
    assert len(results) >= 1

def test_analytics(db):
    if not db.is_connected:
        pytest.skip("MongoDB not available")
    analytics = db.get_analytics()
    assert "total_records" in analytics
    assert "category_distribution" in analytics
    assert "price_stats" in analytics
