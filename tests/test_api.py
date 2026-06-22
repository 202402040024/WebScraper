import pytest
from fastapi.testclient import TestClient
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.main import app

client = TestClient(app)

def test_root():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "service" in data

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] == "healthy"

def test_get_products():
    response = client.get("/products")
    assert response.status_code == 200

def test_get_categories():
    response = client.get("/products/categories")
    assert response.status_code == 200

def test_get_analytics():
    response = client.get("/products/analytics")
    assert response.status_code == 200

def test_get_logs():
    response = client.get("/logs")
    assert response.status_code == 200

def test_scrape_no_url():
    response = client.post("/scrape", json={"url": ""})
    assert response.status_code == 400
