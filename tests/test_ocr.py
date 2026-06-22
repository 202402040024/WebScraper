import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ocr.image_ocr import OCRProcessor, configure_tesseract

def test_configure_tesseract():
    configure_tesseract()
    assert True

def test_ocr_processor_init():
    ocr = OCRProcessor(download_dir="images")
    assert ocr.download_dir == "images"
    assert os.path.exists(ocr.download_dir)

def test_image_filename():
    ocr = OCRProcessor()
    url = "https://books.toscrape.com/media/cache/someimage.jpg"
    filename = ocr._get_image_filename(url)
    assert filename.startswith("img_")
    assert filename.endswith(".jpg")

def test_empty_url():
    ocr = OCRProcessor()
    result = ocr.download_image("")
    assert result == ""
    result = ocr.process_image_url("")
    assert result == ""
