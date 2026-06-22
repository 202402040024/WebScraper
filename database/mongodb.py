import logging
import os
import re
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from pymongo import MongoClient, errors
from pymongo.collection import Collection

logger = logging.getLogger("scraper_dashboard.database")

def clean_price(price_str: Any) -> float:
    """Helper to convert price string (like £51.77 or $19.99) to float."""
    if isinstance(price_str, (int, float)):
        return float(price_str)
    if not price_str:
        return 0.0
    try:
        # Extract digits, decimal point
        cleaned = re.sub(r"[^\d.]", "", str(price_str))
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0

def clean_rating(rating_val: Any) -> float:
    """Helper to normalize rating to a 0.0 - 5.0 float or percentage."""
    if isinstance(rating_val, (int, float)):
        return float(rating_val)
    if not rating_val:
        return 0.0
    
    val_str = str(rating_val).strip().lower()
    
    # Word ratings like One, Two, Three, Four, Five
    word_map = {"one": 1.0, "two": 2.0, "three": 3.0, "four": 4.0, "five": 5.0, "zero": 0.0}
    if val_str in word_map:
        return word_map[val_str]
        
    try:
        # If it is percentage (e.g. "80", "80%")
        if "%" in val_str:
            val_str = val_str.replace("%", "").strip()
            return float(val_str)
        # Parse standard number
        val_float = float(val_str)
        # If rating is 0-100 percentage, we can keep it as is, or normalize it
        return val_float
    except ValueError:
        return 0.0

class MongoDBManager:
    """Manages MongoDB connections, collection operations, data retrieval, and analytics."""

    def __init__(self, uri: Optional[str] = None, db_name: str = None):
        self.uri = uri or os.getenv("MONGO_URI", "mongodb://localhost:27017")
        self.db_name = db_name or os.getenv("DATABASE_NAME", "web_scraper_db")
        self.client: Optional[MongoClient] = None
        self.db = None
        self.products: Optional[Collection] = None
        self.logs: Optional[Collection] = None
        self.is_connected = False
        
        self.connect()

    def connect(self) -> bool:
        """Establish connection to MongoDB."""
        try:
            # Use longer timeout on cloud (Render) — first connect can be slow
            timeout_ms = int(os.getenv("MONGO_TIMEOUT_MS", "10000"))
            self.client = MongoClient(
                self.uri,
                serverSelectionTimeoutMS=timeout_ms,
                connectTimeoutMS=timeout_ms,
                socketTimeoutMS=30000,
                tls=True,
                tlsAllowInvalidCertificates=False,
            )
            # Trigger server_info to verify connection
            self.client.server_info()
            self.db = self.client[self.db_name]
            self.products = self.db["products"]
            self.logs = self.db["scraping_logs"]
            
            # Create indexes
            self.products.create_index("product_url", unique=True)
            self.products.create_index([("name", "text"), ("description", "text")])
            self.logs.create_index("timestamp")
            
            self.is_connected = True
            logger.info(f"Successfully connected to MongoDB: {self.db_name}")
            return True
        except errors.ServerSelectionTimeoutError as e:
            logger.error(f"MongoDB timeout — check Atlas IP whitelist (add 0.0.0.0/0). {e}")
            self.is_connected = False
            return False
        except Exception as e:
            logger.error(f"MongoDB connection error: {e}")
            self.is_connected = False
            return False

    def insert_product(self, product: Dict[str, Any], overwrite: bool = True) -> Tuple[bool, str]:
        """
        Inserts a single scraped product. Prevents duplicates using product_url.
        Normalizes price and rating fields.
        """
        if not self.is_connected:
            return False, "Not connected to MongoDB."
            
        url = product.get("product_url")
        if not url:
            return False, "Product missing product_url."

        # Clean numerical fields for charting/filtering
        product_doc = product.copy()
        product_doc["price_raw"] = product.get("price", "")
        product_doc["price"] = clean_price(product.get("price"))
        product_doc["rating_raw"] = product.get("rating", "")
        product_doc["rating"] = clean_rating(product.get("rating"))
        product_doc["updated_at"] = datetime.utcnow()
        if "scraped_at" not in product_doc:
            product_doc["scraped_at"] = datetime.utcnow()
        else:
            # Parse if string
            if isinstance(product_doc["scraped_at"], str):
                try:
                    product_doc["scraped_at"] = datetime.fromisoformat(product_doc["scraped_at"])
                except ValueError:
                    product_doc["scraped_at"] = datetime.utcnow()

        try:
            # Try to insert
            self.products.insert_one(product_doc)
            return True, "Inserted successfully."
        except errors.DuplicateKeyError:
            if overwrite:
                # Remove _id before update — MongoDB adds it in-place during
                # insert_one, and including it in a replace/update causes an
                # "immutable field _id" error.
                update_doc = {k: v for k, v in product_doc.items() if k != "_id"}
                self.products.update_one(
                    {"product_url": url},
                    {"$set": update_doc}
                )
                return True, "Product updated."
            return False, "Product already exists (skipped)."
        except Exception as e:
            logger.error(f"Error inserting product: {e}")
            return False, str(e)

    def insert_products(self, products: List[Dict[str, Any]], overwrite: bool = True) -> Tuple[int, int]:
        """Inserts multiple products. Returns (inserted_count, error_count)."""
        inserted = 0
        errors_cnt = 0
        for p in products:
            success, _ = self.insert_product(p, overwrite)
            if success:
                inserted += 1
            else:
                errors_cnt += 1
        return inserted, errors_cnt

    def get_products(
        self,
        search_query: Optional[str] = None,
        category: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        min_rating: Optional[float] = None,
        limit: int = 100,
        skip: int = 0
    ) -> List[Dict[str, Any]]:
        """Queries products with flexible filtering criteria."""
        if not self.is_connected:
            return []

        query: Dict[str, Any] = {}

        if search_query:
            query["$text"] = {"$search": search_query}

        if category:
            query["category"] = category

        price_query = {}
        if min_price is not None:
            price_query["$gte"] = min_price
        if max_price is not None:
            price_query["$lte"] = max_price
        if price_query:
            query["price"] = price_query

        if min_rating is not None:
            query["rating"] = {"$gte": min_rating}

        try:
            cursor = self.products.find(query).skip(skip).limit(limit).sort("scraped_at", -1)
            results = list(cursor)
            # Remove mongo object id for serialization
            for doc in results:
                doc["_id"] = str(doc["_id"])
            return results
        except Exception as e:
            logger.error(f"Error fetching products: {e}")
            return []

    def get_categories(self) -> List[str]:
        """Gets all distinct categories from scraped products."""
        if not self.is_connected:
            return []
        try:
            return self.products.distinct("category")
        except Exception as e:
            logger.error(f"Error fetching categories: {e}")
            return []

    def delete_product(self, product_url: str) -> bool:
        """Deletes a single product by URL."""
        if not self.is_connected:
            return False
        try:
            result = self.products.delete_one({"product_url": product_url})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting product: {e}")
            return False

    def clear_database(self) -> bool:
        """Clears all products and logs."""
        if not self.is_connected:
            return False
        try:
            self.products.delete_many({})
            self.logs.delete_many({})
            logger.info("Cleared all products and logs in database.")
            return True
        except Exception as e:
            logger.error(f"Error clearing database: {e}")
            return False

    def get_analytics(self) -> Dict[str, Any]:
        """Performs aggregation to generate metrics and chart details for dashboard."""
        analytics = {
            "total_records": 0,
            "total_images": 0,
            "total_ocr": 0,
            "category_distribution": {},
            "price_stats": {"min": 0.0, "max": 0.0, "avg": 0.0},
            "rating_distribution": {}
        }
        
        if not self.is_connected:
            return analytics

        try:
            total_records = self.products.count_documents({})
            analytics["total_records"] = total_records
            
            # Count records with valid image urls
            analytics["total_images"] = self.products.count_documents(
                {"image_url": {"$ne": "", "$exists": True}}
            )
            
            # Count records with OCR text populated
            analytics["total_ocr"] = self.products.count_documents(
                {"ocr_text": {"$ne": "", "$exists": True}}
            )

            # Category Distribution
            cat_pipeline = [
                {"$group": {"_id": "$category", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}}
            ]
            cat_results = list(self.products.aggregate(cat_pipeline))
            analytics["category_distribution"] = {
                (doc["_id"] or "Unknown"): doc["count"] for doc in cat_results
            }

            # Price Stats
            price_pipeline = [
                {"$group": {
                    "_id": None,
                    "avg_price": {"$avg": "$price"},
                    "min_price": {"$min": "$price"},
                    "max_price": {"$max": "$price"}
                }}
            ]
            price_results = list(self.products.aggregate(price_pipeline))
            if price_results:
                stats = price_results[0]
                analytics["price_stats"] = {
                    "min": round(stats.get("min_price") or 0.0, 2),
                    "max": round(stats.get("max_price") or 0.0, 2),
                    "avg": round(stats.get("avg_price") or 0.0, 2)
                }

            # Rating Analysis
            rating_pipeline = [
                {"$group": {"_id": "$rating", "count": {"$sum": 1}}},
                {"$sort": {"_id": 1}}
            ]
            rating_results = list(self.products.aggregate(rating_pipeline))
            analytics["rating_distribution"] = {
                str(doc["_id"]): doc["count"] for doc in rating_results
            }

        except Exception as e:
            logger.error(f"Error generating database analytics: {e}")

        return analytics

    def log_scraping_run(
        self,
        url: str,
        scraper_type: str,
        status: str,
        items_scraped: int,
        error_msg: Optional[str] = None
    ) -> str:
        """Logs a scraper execution to database for audit history and scheduling."""
        if not self.is_connected:
            return ""
        log_entry = {
            "url": url,
            "scraper_type": scraper_type,
            "status": status,
            "items_scraped": items_scraped,
            "error_message": error_msg,
            "timestamp": datetime.utcnow()
        }
        try:
            res = self.logs.insert_one(log_entry)
            return str(res.inserted_id)
        except Exception as e:
            logger.error(f"Error logging scraping run: {e}")
            return ""

    def get_scraping_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves recent scraping run execution logs."""
        if not self.is_connected:
            return []
        try:
            cursor = self.logs.find({}).sort("timestamp", -1).limit(limit)
            results = list(cursor)
            for doc in results:
                doc["_id"] = str(doc["_id"])
                # format timestamp
                if isinstance(doc["timestamp"], datetime):
                    doc["timestamp"] = doc["timestamp"].isoformat()
            return results
        except Exception as e:
            logger.error(f"Error retrieving scraping logs: {e}")
            return []
