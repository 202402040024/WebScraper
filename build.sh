#!/usr/bin/env bash
set -e

echo "==> Installing core dependencies..."
pip install --no-cache-dir \
    "streamlit>=1.30.0,<2.0.0" \
    "pymongo>=4.6.0" \
    "pytesseract>=0.3.10" \
    "pillow>=10.0.0" \
    "pandas>=2.0.0" \
    "plotly>=5.15.0" \
    "requests>=2.31.0" \
    "beautifulsoup4>=4.12.0" \
    "fake-useragent>=1.1.3" \
    "python-dotenv>=1.0.0" \
    "openpyxl>=3.1.0" \
    "lxml>=4.9.0"

echo "==> Installing Scrapy..."
pip install --no-cache-dir "scrapy>=2.9.0" || echo "WARNING: Scrapy install failed"

echo "==> Installing Selenium..."
pip install --no-cache-dir "selenium>=4.10.0" "webdriver-manager>=4.0.1" || echo "WARNING: Selenium install failed"

echo "==> Installing Playwright..."
pip install --no-cache-dir "playwright>=1.35.0" || echo "WARNING: Playwright install failed"

echo "==> Downloading Playwright Chromium browser..."
python -m playwright install chromium || echo "WARNING: Playwright browser download failed (BS4 fallback will be used)"

echo "==> Installing FastAPI..."
pip install --no-cache-dir "fastapi>=0.100.0" "uvicorn>=0.22.0" || echo "WARNING: FastAPI install failed"

echo "==> Build complete!"
