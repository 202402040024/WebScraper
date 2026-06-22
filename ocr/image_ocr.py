import logging
import os
import hashlib
import requests
from PIL import Image
import pytesseract
from urllib.parse import urlparse

logger = logging.getLogger("scraper_dashboard.ocr")

# =====================================================================
# TESSERACT CONFIGURATION
# =====================================================================
# Local Windows paths as verified in environment
DEFAULT_WINDOWS_TESSDATA = r"D:\Training\webscraping\ocr_scraper\tessdata"
DEFAULT_WINDOWS_EXE = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

def configure_tesseract():
    """Configures Tesseract executable path and TESSDATA_PREFIX dynamically."""
    if os.name == 'nt':  # Windows
        # Set command path
        exe_path = os.getenv("TESSERACT_CMD", DEFAULT_WINDOWS_EXE)
        if os.path.exists(exe_path):
            pytesseract.pytesseract.tesseract_cmd = exe_path
            logger.info(f"Tesseract command path set to: {exe_path}")
        else:
            logger.warning(f"Tesseract executable not found at {exe_path}. OCR may fail.")

        # Set tessdata prefix
        tessdata_path = os.getenv("TESSDATA_PREFIX", DEFAULT_WINDOWS_TESSDATA)
        if os.path.exists(tessdata_path):
            os.environ["TESSDATA_PREFIX"] = tessdata_path
            logger.info(f"TESSDATA_PREFIX set to: {tessdata_path}")
        else:
            logger.warning(f"Tessdata directory not found at {tessdata_path}.")
    else:
        # On Linux/Render, Tesseract is typically installed globally in PATH.
        # We don't override the path, but check if TESSDATA_PREFIX is provided.
        if "TESSDATA_PREFIX" in os.environ:
            logger.info(f"Using TESSDATA_PREFIX from env: {os.environ['TESSDATA_PREFIX']}")
        else:
            logger.info("Using default system Tesseract on non-Windows environment.")

# Initialize configuration
configure_tesseract()


class OCRProcessor:
    """Handles image downloading and OCR text extraction using Tesseract."""

    def __init__(self, download_dir: str = "images"):
        self.download_dir = download_dir
        os.makedirs(self.download_dir, exist_ok=True)
        # In-memory cache for OCR results during the app session
        self._ocr_cache = {}

    def _get_image_filename(self, image_url: str) -> str:
        """Generates a unique and safe filename based on URL hash and original extension."""
        parsed_url = urlparse(image_url)
        path = parsed_url.path
        # Extract extension (default to .jpg)
        ext = os.path.splitext(path)[1]
        if ext.lower() not in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
            ext = '.jpg'
            
        # Hash URL
        url_hash = hashlib.sha256(image_url.encode('utf-8')).hexdigest()[:16]
        return f"img_{url_hash}{ext}"

    def download_image(self, image_url: str) -> str:
        """
        Downloads product image and returns the local file path.
        Returns empty string if download fails.
        """
        if not image_url or not image_url.startswith("http"):
            return ""

        filename = self._get_image_filename(image_url)
        filepath = os.path.join(self.download_dir, filename)

        # Check if already exists
        if os.path.exists(filepath):
            return filepath

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            response = requests.get(image_url, headers=headers, timeout=15)
            if response.status_code == 200:
                with open(filepath, "wb") as f:
                    f.write(response.content)
                logger.info(f"Downloaded image: {image_url} -> {filepath}")
                return filepath
            else:
                logger.warning(f"Failed download image {image_url}, status code: {response.status_code}")
        except Exception as e:
            logger.error(f"Error downloading image {image_url}: {e}")
            
        return ""

    def perform_ocr(self, filepath: str) -> str:
        """
        Performs optical character recognition on local image file.
        Returns extracted text.
        """
        if not filepath or not os.path.exists(filepath):
            return ""

        # Check in cache
        if filepath in self._ocr_cache:
            return self._ocr_cache[filepath]

        try:
            # Open image with Pillow
            with Image.open(filepath) as img:
                # Convert image to RGB if not already
                if img.mode not in ("L", "RGB"):
                    img = img.convert("RGB")
                
                # Perform OCR
                text = pytesseract.image_to_string(img)
                cleaned_text = text.strip()
                
                # Cache results
                self._ocr_cache[filepath] = cleaned_text
                logger.info(f"Successfully performed OCR on {filepath}. Extracted {len(cleaned_text)} characters.")
                return cleaned_text
        except Exception as e:
            logger.error(f"Error performing OCR on {filepath}: {e}")
            return ""

    def process_image_url(self, image_url: str, force_ocr: bool = False) -> str:
        """
        Downloads image from URL and extracts text.
        Combines download and OCR steps.
        """
        if not image_url:
            return ""
            
        # Check cache if URL is already processed
        if image_url in self._ocr_cache and not force_ocr:
            return self._ocr_cache[image_url]

        filepath = self.download_image(image_url)
        if filepath:
            ocr_text = self.perform_ocr(filepath)
            self._ocr_cache[image_url] = ocr_text
            return ocr_text
            
        return ""
