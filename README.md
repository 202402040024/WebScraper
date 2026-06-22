# Advanced Web Scraping Dashboard

A production-ready web scraping dashboard with multiple scraping engines, OCR text extraction, MongoDB storage, and interactive data visualization.

## Features

- **Multiple Scraping Engines**: BeautifulSoup, Selenium, Playwright, Scrapy
- **OCR Integration**: Tesseract-based text extraction from product images
- **MongoDB Storage**: Persistent storage with duplicate detection and analytics
- **Interactive Dashboard**: Streamlit UI with dark mode, glassmorphism design
- **REST API**: FastAPI backend for programmatic access
- **Data Export**: CSV, JSON, Excel, XML formats
- **Visual Analytics**: Price distribution, category breakdowns, rating analysis
- **Scheduler**: Basic job scheduling for recurring scrapes

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium

# Run Streamlit dashboard
streamlit run app.py

# Run FastAPI backend (optional)
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

## Project Structure

```
web_scraper_dashboard/
├── app.py                  # Streamlit dashboard
├── requirements.txt        # Python dependencies
├── Dockerfile              # Container configuration
├── render.yaml             # Render deployment config
├── scrapers/               # Scraping engines
│   ├── base_scraper.py     # Base class with retry, proxy, UA rotation
│   ├── bs4_scraper.py      # BeautifulSoup scraper
│   ├── selenium_scraper.py # Selenium scraper
│   ├── playwright_scraper.py # Playwright scraper (sync + async)
│   └── scrapy_scraper.py   # Scrapy scraper
├── database/
│   └── mongodb.py          # MongoDB manager with CRUD + analytics
├── ocr/
│   └── image_ocr.py        # Tesseract OCR processor
├── api/
│   └── main.py             # FastAPI REST API
├── exports/                # Exported data directory
├── images/                 # Downloaded product images
└── logs/                   # Application logs
```

## Configuration

Environment variables:
- `MONGO_URI`: MongoDB connection string (default: `mongodb://localhost:27017`)
- `TESSERACT_CMD`: Tesseract executable path (Windows only)
- `TESSDATA_PREFIX`: Tesseract language data directory

## Demo Sites

- https://books.toscrape.com/ - Book catalog
- https://demowebshop.tricentis.com/ - E-commerce demo

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/scrape` | Trigger scraping run |
| GET | `/products` | List products with filters |
| GET | `/products/analytics` | Dashboard analytics |
| GET | `/products/categories` | Category list |
| DELETE | `/products/{url}` | Delete product |
| GET | `/logs` | Scraping logs |
| POST | `/ocr/process` | OCR on image URL |

## Deployment

### Docker
```bash
docker build -t scraper-dashboard .
docker run -p 8501:8501 scraper-dashboard
```

### Render
Push to GitHub and connect the repo. Use `render.yaml` for multi-service deployment.
