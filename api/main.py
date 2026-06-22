import logging
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.mongodb import MongoDBManager
from ocr.image_ocr import OCRProcessor
from scrapers.bs4_scraper import BS4Scraper
from scrapers.selenium_scraper import SeleniumScraper
from scrapers.playwright_scraper import PlaywrightScraper
from scrapers.scrapy_scraper import ScrapyScraper

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scraper_dashboard.api")

app = FastAPI(
    title="Web Scraper Dashboard API",
    description="REST API for triggering scrapes, querying products, logs, and OCR results.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = MongoDBManager()
ocr = OCRProcessor(download_dir="images")

class ScrapeRequest(BaseModel):
    url: str
    scraper_type: str = "bs4"
    max_pages: int = 1
    proxy: Optional[str] = None
    enable_ocr: bool = False

class ScrapeResponse(BaseModel):
    status: str
    items_scraped: int
    message: str

def get_scraper(scraper_type: str, proxy: Optional[str] = None):
    scrapers = {
        "bs4": BS4Scraper,
        "selenium": SeleniumScraper,
        "playwright": PlaywrightScraper,
        "scrapy": ScrapyScraper,
    }
    cls = scrapers.get(scraper_type)
    if not cls:
        raise HTTPException(status_code=400, detail=f"Unknown scraper type: {scraper_type}")
    kwargs = {"delay": 0.5, "retries": 2}
    if proxy:
        kwargs["proxies"] = proxy
    return cls(**kwargs)

@app.get("/")
def root():
    return {"service": "Web Scraper Dashboard API", "status": "running"}

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "mongo_connected": db.is_connected,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/scrape", response_model=ScrapeResponse)
def run_scrape(req: ScrapeRequest):
    if not req.url:
        raise HTTPException(status_code=400, detail="URL is required.")
    try:
        scraper = get_scraper(req.scraper_type, req.proxy)
        items = scraper.scrape(req.url, max_pages=req.max_pages)
        inserted, errors = db.insert_products(items)
        if req.enable_ocr:
            for item in items:
                if item.get("image_url"):
                    ocr_text = ocr.process_image_url(item["image_url"])
                    if ocr_text:
                        db.products.update_one(
                            {"product_url": item["product_url"]},
                            {"$set": {"ocr_text": ocr_text}}
                        )
        db.log_scraping_run(
            url=req.url,
            scraper_type=req.scraper_type,
            status="success",
            items_scraped=len(items)
        )
        return ScrapeResponse(
            status="success",
            items_scraped=len(items),
            message=f"Scraped {len(items)} items. Inserted: {inserted}, Errors: {errors}"
        )
    except Exception as e:
        logger.error(f"Scrape failed: {e}")
        db.log_scraping_run(
            url=req.url,
            scraper_type=req.scraper_type,
            status="failed",
            items_scraped=0,
            error_msg=str(e)
        )
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/products")
def get_products(
    search: Optional[str] = None,
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_rating: Optional[float] = None,
    limit: int = Query(default=100, le=500),
    skip: int = 0
):
    return db.get_products(
        search_query=search,
        category=category,
        min_price=min_price,
        max_price=max_price,
        min_rating=min_rating,
        limit=limit,
        skip=skip
    )

@app.get("/products/categories")
def get_categories():
    return {"categories": db.get_categories()}

@app.get("/products/analytics")
def get_analytics():
    return db.get_analytics()

@app.delete("/products/{product_url:path}")
def delete_product(product_url: str):
    success = db.delete_product(product_url)
    if not success:
        raise HTTPException(status_code=404, detail="Product not found.")
    return {"status": "deleted"}

@app.delete("/products")
def clear_products():
    db.clear_database()
    return {"status": "cleared"}

@app.get("/logs")
def get_logs(limit: int = 50):
    return db.get_scraping_logs(limit=limit)

@app.post("/ocr/process")
def ocr_process(image_url: str = Query(...)):
    text = ocr.process_image_url(image_url)
    return {"image_url": image_url, "ocr_text": text}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
