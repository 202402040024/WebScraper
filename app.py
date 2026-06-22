import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json
import os
import sys
import shutil
import logging
from datetime import datetime
from io import BytesIO
from dotenv import load_dotenv

load_dotenv()  # loads .env locally; no-op on Render where env vars are set directly

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.mongodb import MongoDBManager
from ocr.image_ocr import OCRProcessor
from scrapers.bs4_scraper import BS4Scraper
from scrapers.selenium_scraper import SeleniumScraper
from scrapers.playwright_scraper import PlaywrightScraper
from scrapers.scrapy_scraper import ScrapyScraper
from scrapers.scrapingbee_scraper import ScrapingBeeScraper

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scraper_dashboard.streamlit")


def _browser_available() -> bool:
    """Check if a usable Chrome/Chromium binary exists on this system."""
    for candidate in [
        "/usr/bin/chromium", "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable",
    ]:
        if os.path.exists(candidate):
            return True
    if shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome"):
        return True
    # Windows: check for Chrome in common install paths
    if os.name == "nt":
        win_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
        return any(os.path.exists(p) for p in win_paths)
    return False


BROWSER_AVAILABLE = _browser_available()

st.set_page_config(
    page_title="Web Scraper Dashboard",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .stApp { background-color: #0f172a; }
    .css-1d391kg, .css-12oz5g7 { background-color: #1e293b; }
    .st-bx, .st-cf, .st-cg, .st-ch, .st-ci, .st-cj { background-color: #1e293b; }
    div[data-testid="stSidebar"] { background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%); border-right: 1px solid rgba(99, 102, 241, 0.2); }
    div[data-testid="stSidebar"] h1, div[data-testid="stSidebar"] h2, div[data-testid="stSidebar"] h3 { color: #e2e8f0; }
    .stButton>button { background: linear-gradient(135deg, #6366f1, #818cf8); border: none; border-radius: 8px; color: white; font-weight: 600; padding: 0.5rem 2rem; transition: all 0.3s; box-shadow: 0 4px 14px rgba(99, 102, 241, 0.4); }
    .stButton>button:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(99, 102, 241, 0.6); }
    .stButton>button:active { transform: translateY(0); }
    div.stDataFrame { border-radius: 12px; overflow: hidden; border: 1px solid #334155; }
    .stDataFrame thead tr th { background-color: #1e293b !important; color: #f1f5f9 !important; }
    .card { background: rgba(30, 41, 59, 0.8); backdrop-filter: blur(10px); border: 1px solid rgba(99, 102, 241, 0.2); border-radius: 16px; padding: 1.5rem; margin-bottom: 1rem; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3); }
    .stat-value { font-size: 2rem; font-weight: 700; color: #818cf8; }
    .stat-label { font-size: 0.875rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.1em; }
    .section-title { color: #e2e8f0; font-weight: 600; font-size: 1.25rem; margin-bottom: 1rem; border-bottom: 2px solid #6366f1; padding-bottom: 0.5rem; }
    .success-text { color: #10b981; }
    .warning-text { color: #f59e0b; }
    .stSelectbox label, .stNumberInput label, .stCheckbox label, .stTextInput label { color: #cbd5e1 !important; }
    .stSelectbox > div > div { background-color: #1e293b; border-color: #334155; color: #f8fafc; }
    .stNumberInput > div > div { background-color: #1e293b; border-color: #334155; color: #f8fafc; }
    .stTextInput > div > div { background-color: #1e293b; border-color: #334155; color: #f8fafc; }
    .stMultiSelect > div > div { background-color: #1e293b; border-color: #334155; color: #f8fafc; }
    .stSelectbox > div > div > div { color: #f8fafc; }
    h1, h2, h3, h4, h5, h6, p, span, div { color: #f1f5f9; }
    .stTabs [data-baseweb="tab-list"] { background-color: #1e293b; border-radius: 12px; padding: 4px; gap: 2px; }
    .stTabs [data-baseweb="tab"] { border-radius: 8px; color: #94a3b8; padding: 8px 16px; }
    .stTabs [aria-selected="true"] { background-color: #6366f1; color: white !important; }
    [data-testid="stExpander"] { background-color: #1e293b; border-radius: 12px; border: 1px solid #334155; }
    ::-webkit-scrollbar { width: 8px; height: 8px; }
    ::-webkit-scrollbar-track { background: #0f172a; }
    ::-webkit-scrollbar-thumb { background: #6366f1; border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: #818cf8; }
    .stAlert { border-radius: 12px; }
    div[role="alert"] { border-radius: 12px; }
    img { border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

db = MongoDBManager()
ocr = OCRProcessor(download_dir="images")

# Show a visible error if MongoDB failed to connect on startup
if not db.is_connected:
    st.error(
        "❌ **MongoDB not connected.** Scraped data cannot be saved. "
        "Check: 1) MONGO_URI env var is set correctly on Render, "
        "2) MongoDB Atlas → Network Access → Add IP **0.0.0.0/0** (allow all). "
        f"URI starts with: `{db.uri[:40]}...`"
    )

def get_analytics_cached(_cache_key: int = 0):
    return db.get_analytics()

def get_products_cached(limit: int, search_query: str, category: str,
                        min_rating: float, _cache_key: int = 0):
    kwargs = {}
    if search_query:
        kwargs["search_query"] = search_query
    if category and category != "All":
        kwargs["category"] = category
    if min_rating:
        kwargs["min_rating"] = min_rating
    return db.get_products(limit=limit, **kwargs)

def get_categories_cached(_cache_key: int = 0):
    return db.get_categories()

def get_logs_cached(_cache_key: int = 0):
    return db.get_scraping_logs(limit=100)

SCRAPER_MAP = {
    "BeautifulSoup (BS4)": "bs4",
    "Selenium": "selenium",
    "Playwright": "playwright",
    "Scrapy": "scrapy"
}

SCRAPINGBEE_KEY = os.getenv("SCRAPINGBEE_API_KEY", "")

def get_scraper_instance(scraper_key: str, proxy: str = ""):
    scraper_type = SCRAPER_MAP[scraper_key]
    kwargs = {"delay": 0.5, "retries": 2}
    if proxy:
        kwargs["proxies"] = proxy

    # On Render (no Chrome): Selenium/Playwright use ScrapingBee if API key is set,
    # otherwise fall back to BS4.
    if scraper_type in ("selenium", "playwright") and not BROWSER_AVAILABLE:
        if SCRAPINGBEE_KEY:
            st.info(f"🌐 **{scraper_key}** → using **ScrapingBee** cloud browser (no local Chrome needed)")
            return ScrapingBeeScraper(**kwargs)
        else:
            st.warning(
                f"⚠️ **{scraper_key}** needs Chrome (not available on this server). "
                f"Add a **SCRAPINGBEE_API_KEY** env var on Render for cloud browser support, "
                f"or use **BS4 / Scrapy** which work natively. Falling back to BS4 now."
            )
            return BS4Scraper(**kwargs)

    if scraper_type == "bs4":
        return BS4Scraper(**kwargs)
    elif scraper_type == "selenium":
        return SeleniumScraper(**kwargs)
    elif scraper_type == "playwright":
        return PlaywrightScraper(**kwargs)
    elif scraper_type == "scrapy":
        return ScrapyScraper(**kwargs)
    return None

def run_scrape_task(url: str, scraper_key: str, max_pages: int, proxy: str, enable_ocr: bool):
    st.info(f"Starting {scraper_key} scrape of {url}...")
    progress_bar = st.progress(0)
    status_text = st.empty()
    try:
        scraper = get_scraper_instance(scraper_key, proxy)
        if not scraper:
            st.error("Invalid scraper selected.")
            return [], 0, 0
        status_text.text("Scraping in progress...")
        progress_bar.progress(30)
        items = scraper.scrape(url, max_pages=max_pages)
        progress_bar.progress(70)

        if not items:
            st.warning("No items were scraped. Check the URL or page structure.")
            return [], 0, 0

        status_text.text(f"Saving {len(items)} items to database...")

        if db.is_connected:
            inserted, errors = db.insert_products(items)
        else:
            st.warning("MongoDB not connected — results scraped but not saved.")
            inserted, errors = 0, 0

        if enable_ocr:
            status_text.text("Running OCR on product images...")
            for i, item in enumerate(items):
                if item.get("image_url"):
                    ocr_text = ocr.process_image_url(item["image_url"])
                    if ocr_text and db.is_connected:
                        db.products.update_one(
                            {"product_url": item["product_url"]},
                            {"$set": {"ocr_text": ocr_text}}
                        )
                progress_bar.progress(70 + int((i + 1) / len(items) * 20))

        if db.is_connected:
            db.log_scraping_run(
                url=url, scraper_type=scraper_key,
                status="success", items_scraped=len(items)
            )
        progress_bar.progress(100)
        status_text.text("Complete!")
        st.success(f"✅ Scraped **{len(items)}** products. Saved: **{inserted}**, Updated: **{len(items)-inserted}**")
        st.session_state["scrape_done"] = True
        return items, inserted, errors

    except Exception as e:
        logger.error(f"Scrape failed: {e}")
        st.error(f"Scraping failed: {e}")
        try:
            if db.is_connected:
                db.log_scraping_run(
                    url=url, scraper_type=scraper_key,
                    status="failed", items_scraped=0, error_msg=str(e)
                )
        except Exception:
            pass
        return [], 0, 0

st.title(" Advanced Web Scraping Dashboard")
st.markdown("<p style='color: #94a3b8; margin-top: -0.5rem;'>Production-ready multi-engine scraper with OCR, MongoDB, and analytics</p>", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("##  Scraper Control Panel")
    st.markdown("<hr style='border-color: #334155;'>", unsafe_allow_html=True)

    target_url = st.text_input(
        "Target URL",
        value="https://books.toscrape.com/",
        help="Enter the URL of the site you want to scrape."
    )

    scraper_choice = st.selectbox(
        "Scraping Engine",
        options=list(SCRAPER_MAP.keys()),
        index=0
    )

    col1, col2 = st.columns(2)
    with col1:
        max_pages = st.number_input("Max Pages", min_value=1, max_value=50, value=2)
    with col2:
        delay = st.number_input("Delay (s)", min_value=0.0, max_value=10.0, value=0.5, step=0.5)

    proxy_input = st.text_input("Proxy (optional)", placeholder="http://user:pass@host:port")

    enable_ocr = st.checkbox(" Enable OCR on Images", value=False, help="Extract text from product images using Tesseract.")

    st.markdown("<hr style='border-color: #334155;'>", unsafe_allow_html=True)

    scrape_btn = st.button(" Start Scraping", use_container_width=True)

    # Show environment capabilities
    st.markdown("<hr style='border-color: #334155;'>", unsafe_allow_html=True)
    if not BROWSER_AVAILABLE:
        if SCRAPINGBEE_KEY:
            st.success("🌐 Cloud browser ready (ScrapingBee) — all scrapers available")
        else:
            st.info("ℹ️ BS4 & Scrapy work here. Add SCRAPINGBEE_API_KEY for Selenium/Playwright support.")
    else:
        st.success("✅ Browser detected — all scrapers available.")

    st.markdown("<hr style='border-color: #334155;'>", unsafe_allow_html=True)

    st.markdown("###  Export Data")
    export_format = st.selectbox("Format", ["CSV", "JSON", "Excel", "XML"], index=0)
    export_btn = st.button(" Export Products", use_container_width=True)

    if export_btn:
        products = get_products_cached(5000, "", "", 0, _cache_key=st.session_state.get("cache_key", 0))
        if products:
            df = pd.DataFrame(products)
            cols = [c for c in ["name", "price", "rating", "category", "description", "product_url", "image_url", "ocr_text"] if c in df.columns]
            df = df[cols]
            if export_format == "CSV":
                csv = df.to_csv(index=False).encode("utf-8")
                st.download_button(" Download CSV", csv, "products.csv", "text/csv")
            elif export_format == "JSON":
                j = df.to_json(orient="records", indent=2).encode("utf-8")
                st.download_button(" Download JSON", j, "products.json", "application/json")
            elif export_format == "Excel":
                buf = BytesIO()
                with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                    df.to_excel(writer, index=False, sheet_name="Products")
                st.download_button(" Download Excel", buf.getvalue(), "products.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            elif export_format == "XML":
                xml = df.to_xml(index=False).encode("utf-8")
                st.download_button(" Download XML", xml, "products.xml", "application/xml")
        else:
            st.warning("No products to export.")

    st.markdown("<hr style='border-color: #334155;'>", unsafe_allow_html=True)
    st.caption(f"DB Status: {' Connected' if db.is_connected else ' Disconnected'}")
    tesseract_path = os.getenv("TESSERACT_CMD", r'C:\Program Files\Tesseract-OCR\tesseract.exe')
    ocr_status = ' Ready' if os.path.exists(tesseract_path) else ' Not Found'
    st.caption(f"OCR Engine: {ocr_status}")

if scrape_btn:
    if not target_url:
        st.error("Please enter a URL.")
    else:
        st.session_state["scrape_done"] = False
        with st.container():
            run_scrape_task(target_url, scraper_choice, int(max_pages), proxy_input, enable_ocr)

# Rerun AFTER showing the result so analytics tab refreshes with new data
if st.session_state.get("scrape_done"):
    st.session_state["scrape_done"] = False
    st.rerun()

tab1, tab2, tab3, tab4, tab5 = st.tabs([" Analytics", " Products", " Image Gallery", " Scraping Logs", "  Scheduler"])

with tab1:
    st.markdown("<div class='section-title'> Dashboard Analytics</div>", unsafe_allow_html=True)

    _ck = st.session_state.get("cache_key", 0)
    analytics = get_analytics_cached(_cache_key=_ck)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f"""
        <div class='card' style='text-align: center;'>
            <div class='stat-value'>{analytics['total_records']}</div>
            <div class='stat-label'>Total Products</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class='card' style='text-align: center;'>
            <div class='stat-value'>{analytics['total_images']}</div>
            <div class='stat-label'>With Images</div>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown(f"""
        <div class='card' style='text-align: center;'>
            <div class='stat-value'>{analytics['total_ocr']}</div>
            <div class='stat-label'>OCR Processed</div>
        </div>
        """, unsafe_allow_html=True)
    with col4:
        st.markdown(f"""
        <div class='card' style='text-align: center;'>
            <div class='stat-value'>{len(analytics.get('category_distribution', {}))}</div>
            <div class='stat-label'>Categories</div>
        </div>
        """, unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        cat_dist = analytics.get("category_distribution", {})
        if cat_dist:
            cat_df = pd.DataFrame(list(cat_dist.items()), columns=["Category", "Count"]).sort_values("Count", ascending=False)
            fig = px.bar(cat_df, x="Category", y="Count", title="Products by Category",
                         color="Count", color_continuous_scale="blues",
                         text="Count", height=400)
            fig.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                              font_color="#e2e8f0", title_font_color="#f1f5f9",
                              margin=dict(l=20, r=20, t=40, b=20), xaxis_title=None)
            fig.update_traces(marker_line_color="#6366f1", marker_line_width=1.5, textposition="outside")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No category data available.")
        st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        price_stats = analytics.get("price_stats", {})
        if price_stats.get("avg", 0) > 0:
            metrics_col1, metrics_col2, metrics_col3 = st.columns(3)
            metrics_col1.metric(" Min Price", f"${price_stats['min']:.2f}")
            metrics_col2.metric(" Avg Price", f"${price_stats['avg']:.2f}")
            metrics_col3.metric(" Max Price", f"${price_stats['max']:.2f}")

            products_with_price = get_products_cached(500, "", "", 0, _cache_key=_ck)
            prices = [p.get("price", 0) for p in products_with_price if p.get("price", 0) > 0]
            if prices:
                price_df = pd.DataFrame({"Price": prices})
                fig2 = px.histogram(price_df, x="Price", nbins=20, title="Price Distribution",
                                    color_discrete_sequence=["#6366f1"], height=300)
                fig2.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                                   font_color="#e2e8f0", title_font_color="#f1f5f9",
                                   margin=dict(l=20, r=20, t=40, b=20))
                st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("No price data available yet.")
        st.markdown("</div>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        rating_dist = analytics.get("rating_distribution", {})
        if rating_dist:
            rating_df = pd.DataFrame(list(rating_dist.items()), columns=["Rating", "Count"]).sort_values("Rating")
            fig3 = px.pie(rating_df, values="Count", names="Rating", title="Rating Distribution",
                          color_discrete_sequence=px.colors.sequential.Blues_r, hole=0.4)
            fig3.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                               font_color="#e2e8f0", title_font_color="#f1f5f9",
                               margin=dict(l=20, r=20, t=40, b=20))
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.info("No rating data available.")
        st.markdown("</div>", unsafe_allow_html=True)
    with col2:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("<div style='font-size: 1.1rem; font-weight: 600; color: #e2e8f0; margin-bottom: 1rem;'>Database Health</div>", unsafe_allow_html=True)
        st.markdown(f"""
        <div style='display: flex; justify-content: space-between; padding: 0.5rem 0; border-bottom: 1px solid #334155;'>
            <span style='color: #94a3b8;'>MongoDB Status</span>
            <span style='color: {"#10b981" if db.is_connected else "#ef4444"};'>{'Connected' if db.is_connected else 'Disconnected'}</span>
        </div>
        <div style='display: flex; justify-content: space-between; padding: 0.5rem 0; border-bottom: 1px solid #334155;'>
            <span style='color: #94a3b8;'>Total Records</span>
            <span style='color: #f1f5f9;'>{analytics['total_records']}</span>
        </div>
        <div style='display: flex; justify-content: space-between; padding: 0.5rem 0; border-bottom: 1px solid #334155;'>
            <span style='color: #94a3b8;'>OCR Records</span>
            <span style='color: #f1f5f9;'>{analytics['total_ocr']}</span>
        </div>
        <div style='display: flex; justify-content: space-between; padding: 0.5rem 0;'>
            <span style='color: #94a3b8;'>Categories Found</span>
            <span style='color: #f1f5f9;'>{len(analytics.get('category_distribution', {}))}</span>
        </div>
        """, unsafe_allow_html=True)
        if db.is_connected:
            if st.button(" Clear All Data", type="secondary", use_container_width=True):
                db.clear_database()
                st.success("Database cleared!")
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

with tab2:
    st.markdown("<div class='section-title'> Product Catalog</div>", unsafe_allow_html=True)

    _ck = st.session_state.get("cache_key", 0)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        search_query = st.text_input(" Search", placeholder="Search products...")
    with col2:
        categories = get_categories_cached(_cache_key=_ck)
        cat_options = ["All"] + categories
        selected_category = st.selectbox(" Category", cat_options)
    with col3:
        min_r = st.selectbox(" Min Rating", ["Any", "1", "2", "3", "4", "5"])
    with col4:
        sort_by = st.selectbox(" Sort By", ["Newest First", "Price: Low to High", "Price: High to Low", "Rating: High to Low"])

    min_rating_val = float(min_r) if min_r and min_r != "Any" else 0
    products = get_products_cached(
        500, search_query or "",
        selected_category if selected_category != "All" else "",
        min_rating_val, _cache_key=_ck
    )

    if sort_by == "Price: Low to High":
        products.sort(key=lambda x: x.get("price", 0) or 0)
    elif sort_by == "Price: High to Low":
        products.sort(key=lambda x: x.get("price", 0) or 0, reverse=True)
    elif sort_by == "Rating: High to Low":
        products.sort(key=lambda x: x.get("rating", 0) or 0, reverse=True)

    if products:
        df_display = pd.DataFrame(products)
        display_cols = ["name", "price", "rating", "category", "scraper_type", "product_url"]
        available = [c for c in display_cols if c in df_display.columns]
        df_table = df_display[available].copy()
        if "price" in df_table.columns:
            df_table["price"] = df_table["price"].apply(lambda x: f"${float(x or 0):.2f}")
        if "rating" in df_table.columns:
            df_table["rating"] = df_table["rating"].apply(lambda x: f"{float(x or 0):.1f}")

        st.dataframe(
            df_table,
            use_container_width=True,
            height=500,
            column_config={
                "product_url": st.column_config.LinkColumn("URL", display_text="Open"),
                "name": st.column_config.TextColumn("Name", width="large"),
                "price": st.column_config.TextColumn("Price", width="small"),
                "rating": st.column_config.TextColumn("Rating", width="small"),
            }
        )
        st.caption(f"Showing {len(products)} products")
    else:
        st.info("No products found. Run a scrape task first!")

with tab3:
    st.markdown("<div class='section-title'> Image Gallery & OCR Results</div>", unsafe_allow_html=True)

    ocr_products = get_products_cached(200, "", "", 0, _cache_key=st.session_state.get("cache_key", 0))
    ocr_products = [p for p in ocr_products if p.get("image_url")]

    if ocr_products:
        cols = st.columns(4)
        for i, product in enumerate(ocr_products[:24]):
            with cols[i % 4]:
                img_url = product.get("image_url", "")
                name = product.get("name", "Unknown")
                ocr_text = product.get("ocr_text", "")
                price = product.get("price", "")
                st.markdown(f"""
                <div class='card' style='padding: 0.75rem; text-align: center;'>
                    <img src='{img_url}' style='width: 100%; height: 150px; object-fit: contain; margin-bottom: 0.5rem;' onerror="this.style.display='none'">
                    <div style='font-size: 0.8rem; font-weight: 600; color: #e2e8f0;'>{name[:40]}</div>
                    <div style='font-size: 0.8rem; color: #818cf8;'>{f"${float(price or 0):.2f}" if price else ""}</div>
                </div>
                """, unsafe_allow_html=True)
                if ocr_text:
                    with st.expander(" OCR Text", expanded=False):
                        st.code(ocr_text[:200], language="text")
                else:
                    if enable_ocr and st.button(f" OCR", key=f"ocr_{i}", use_container_width=True):
                        with st.spinner("Processing..."):
                            text = ocr.process_image_url(img_url)
                            if text and db.is_connected:
                                db.products.update_one(
                                    {"product_url": product["product_url"]},
                                    {"$set": {"ocr_text": text}}
                                )
                            st.rerun()
    else:
        st.info("No product images found. Scrape a site and enable OCR to see results here.")

with tab4:
    st.markdown("<div class='section-title'> Scraping Run History</div>", unsafe_allow_html=True)

    logs = get_logs_cached(_cache_key=st.session_state.get("cache_key", 0))
    if logs:
        log_df = pd.DataFrame(logs)
        log_df["timestamp"] = pd.to_datetime(log_df["timestamp"]).dt.strftime("%Y-%m-%d %H:%M:%S") if "timestamp" in log_df.columns else ""
        display_logs = ["timestamp", "url", "scraper_type", "status", "items_scraped"]
        available_logs = [c for c in display_logs if c in log_df.columns]
        st.dataframe(log_df[available_logs], use_container_width=True, height=400)

        st.markdown("<div class='section-title' style='margin-top: 2rem;'> Run Statistics</div>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Runs", len(log_df))
        with col2:
            success_count = len(log_df[log_df["status"] == "success"]) if "status" in log_df.columns else 0
            st.metric("Successful", success_count)
        with col3:
            failed_count = len(log_df[log_df["status"] == "failed"]) if "status" in log_df.columns else 0
            st.metric("Failed", failed_count)

        if "status" in log_df.columns and "items_scraped" in log_df.columns:
            fig_log = px.bar(log_df.head(20), x="timestamp", y="items_scraped", color="status",
                             title="Recent Scraping Runs", barmode="group",
                             color_discrete_map={"success": "#10b981", "failed": "#ef4444"})
            fig_log.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                                  font_color="#e2e8f0", title_font_color="#f1f5f9")
            st.plotly_chart(fig_log, use_container_width=True)
    else:
        st.info("No scraping logs yet. Run a scrape task to see history here.")

with tab5:
    st.markdown("<div class='section-title'> Scraping Scheduler</div>", unsafe_allow_html=True)
    st.markdown("""
    <div class='card'>
        <p style='color: #94a3b8;'>Schedule recurring scraping jobs. Jobs run on a background thread when the dashboard is active.</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        scheduled_url = st.text_input("URL to Scrape", value="https://books.toscrape.com/", key="sched_url")
        sched_scraper = st.selectbox("Scraper", list(SCRAPER_MAP.keys()), key="sched_scraper")
    with col2:
        sched_interval = st.selectbox("Interval", ["Every 5 minutes", "Every 15 minutes", "Every 30 minutes", "Every hour", "Every 6 hours", "Daily"])
        sched_pages = st.number_input("Pages", min_value=1, max_value=20, value=2, key="sched_pages")

    if "scheduled_jobs" not in st.session_state:
        st.session_state.scheduled_jobs = []

    col1, col2 = st.columns(2)
    with col1:
        if st.button(" Schedule Job", use_container_width=True):
            job = {
                "url": scheduled_url,
                "scraper": sched_scraper,
                "interval": sched_interval,
                "pages": int(sched_pages),
                "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            st.session_state.scheduled_jobs.append(job)
            st.success(f"Scheduled {sched_scraper} on {scheduled_url} ({sched_interval})")
    with col2:
        if st.button(" Clear All Jobs", use_container_width=True):
            st.session_state.scheduled_jobs = []
            st.rerun()

    if st.session_state.scheduled_jobs:
        sched_df = pd.DataFrame(st.session_state.scheduled_jobs)
        st.dataframe(sched_df, use_container_width=True)
    else:
        st.info("No scheduled jobs. Create one above.")
