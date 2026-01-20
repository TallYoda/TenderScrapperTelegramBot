import os
import json
import logging
import psycopg
import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from config_loader import get_required_config

# ---------- CONFIG ----------
BASE_URL = "https://tender.2merkato.com/tenders/free?page={}"
PAGES_TO_SCRAPE = 2  # Change to 50 later
CONFIG = get_required_config(["DB_URL"])
DB_URL = CONFIG["DB_URL"]
# ---------- LOGGING ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ---------- DB SETUP ----------
def init_db():
    conn = psycopg.connect(DB_URL, sslmode="require")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tenders1 (
            id TEXT PRIMARY KEY,
            title TEXT,
            url TEXT,
            bid_closing_date TEXT,
            bid_opening_date TEXT,
            published_on TEXT
        )
    """)
    conn.commit()
    cur.close()
    conn.close()
    logging.info("✅ Database initialized")

def load_existing_ids():
    conn = psycopg.connect(DB_URL, sslmode="require")
    cur = conn.cursor()
    cur.execute("SELECT id FROM tenders1;")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return set(row[0] for row in rows)

def insert_tender(tender, existing_ids):
    tender_id = tender["id"]
    if tender_id in existing_ids:
        logging.info(f"↩️ Skipping existing tender: {tender['title']}")
        return
    conn = psycopg.connect(DB_URL, sslmode="require")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO tenders1 (id, title, url, bid_closing_date, bid_opening_date, published_on)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
    """, (
        tender_id,
        tender["title"],
        tender["url"],
        tender.get("bid_closing_date"),
        tender.get("bid_opening_date"),
        tender.get("published_on")
    ))
    conn.commit()
    cur.close()
    conn.close()
    existing_ids.add(tender_id)
    logging.info(f"💾 Saved: {tender['title']}")

# ---------- SCRAPER ----------
async def scrape_page(page, page_num, existing_ids):
    url = BASE_URL.format(page_num)
    logging.info(f"📄 Scraping page {page_num} → {url}")
    await page.goto(url, timeout=60000)
    await page.wait_for_selector("h3.font-medium.text-lg.tracking-wide.leading-6 a", timeout=15000)

    html = await page.content()
    soup = BeautifulSoup(html, "html.parser")
    tenders = []

    h3_tags = soup.select("h3.font-medium.text-lg.tracking-wide.leading-6")

    seen_ids = set()
    for h3 in h3_tags:
        try:
            a_tag = h3.select_one("a")
            title = a_tag.get_text(strip=True)
            href = a_tag["href"].strip()
            full_url = href if href.startswith("http") else "https://tender.2merkato.com" + href
            id = full_url.rstrip('/').split('/')[-1]
            if id in seen_ids or id in existing_ids:
                continue
            seen_ids.add(id)
            detail_div = h3.find_parent().find_next_sibling("div")
            closing_date = opening_date = published_on = None

            if detail_div:
                for row in detail_div.select("div.flex.gap-x-4"):
                    label = row.select_one("div.font-medium")
                    if not label:
                        continue
                    value_div = label.find_next_sibling("div")
                    label_text = label.get_text(strip=True)
                    value_text = value_div.get_text(strip=True) if value_div else ""

                    if "closing date" in label_text.lower():
                        closing_date = value_text
                    elif "opening date" in label_text.lower():
                        opening_date = value_text
                    elif "published" in label_text.lower():
                        published_on = value_text

            tender_data = {
                "id":id,
                "title": title,
                "url": full_url,
                "bid_closing_date": closing_date,
                "bid_opening_date": opening_date,
                "published_on": published_on
            }
            tenders.append(tender_data)
        except Exception as e:
            logging.warning(f"⚠️ Skipping tender: {e}")

    return tenders

# ---------- MAIN ----------
async def main():
    init_db()
    existing_ids = load_existing_ids()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for i in range(1, PAGES_TO_SCRAPE + 1):
            tenders = await scrape_page(page, i, existing_ids)
            for tender in tenders:
                insert_tender(tender, existing_ids)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
