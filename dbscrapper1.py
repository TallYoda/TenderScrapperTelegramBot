import asyncio
import asyncpg
import logging
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import os
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

DB_URL = os.getenv("postgresql://tendertable_user:UbNODwcnwuyzkoBBpY7mQcPdD9n0SgL3@dpg-d2f4kdruibrs73f9eaf0-a.frankfurt-postgres.render.com/tendertable")  # Render gives you this env var
BASE_URL = "https://tender.2merkato.com/tenders/free?page={}"

detail_fields = {
    "bid closing date": "bid_closing_date",
    "bid opening date": "bid_opening_date",
    "published on": "published_on"
}

async def init_db():
    conn = await asyncpg.connect(DB_URL, ssl="require")
    #conn = await asyncpg.connect(DB_URL)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS tenders (
            id SERIAL PRIMARY KEY,
            title TEXT,
            url TEXT UNIQUE,
            bid_closing_date TEXT,
            bid_opening_date TEXT,
            published_on TEXT,
            scraped_at TIMESTAMP DEFAULT NOW()
        )
    """)
    await conn.close()

async def scrape_page(page, page_number):
    url = BASE_URL.format(page_number)
    logging.info(f"Scraping page {page_number} → {url}")
    await page.goto(url, timeout=60000)
    await page.wait_for_selector("h3.font-medium.text-lg.tracking-wide.leading-6 a", timeout=20000)

    html = await page.content()
    soup = BeautifulSoup(html, "lxml")
    tenders = []

    h3_tags = soup.select("h3.font-medium.text-lg.tracking-wide.leading-6")

    for h3 in h3_tags:
        try:
            a_tag = h3.select_one("a")
            if not a_tag:
                continue

            title = a_tag.get_text(strip=True)
            href = a_tag["href"].strip()
            full_url = "https://tender.2merkato.com" + href if href.startswith("/") else href

            # Get bid dates & published
            detail_div = h3.find_parent().find_next_sibling("div")
            closing_date = opening_date = published_on = None

            if detail_div:
                for row in detail_div.select("div.flex.gap-x-4"):
                    label = row.select_one("div.font-medium")
                    if not label:
                        continue
                    value_div = label.find_next_sibling("div")
                    label_text = label.get_text(strip=True).rstrip(":").lower()
                    value_text = value_div.get_text(strip=True) if value_div else ""
                    key = detail_fields.get(label_text)
                    if key == "bid_closing_date":
                        closing_date = value_text
                    elif key == "bid_opening_date":
                        opening_date = value_text
                    elif key == "published_on":
                        published_on = value_text

            tenders.append({
                "title": title,
                "url": full_url,
                "bid_closing_date": closing_date,
                "bid_opening_date": opening_date,
                "published_on": published_on
            })

        except Exception as e:
            logging.warning(f"⚠️ Skipping tender: {e}")

    return tenders

async def save_to_db(data):
    conn = await asyncpg.connect(DB_URL)
    for tender in data:
        try:
            await conn.execute("""
                INSERT INTO tenders (title, url, bid_closing_date, bid_opening_date, published_on, scraped_at)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (url) DO NOTHING
            """, tender["title"], tender["url"], tender["bid_closing_date"], tender["bid_opening_date"], tender["published_on"], datetime.utcnow())
        except Exception as e:
            logging.warning(f"⚠️ Failed to insert: {e}")
    await conn.close()

async def main():
    await init_db()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for i in range(1, 51):  # First 50 pages
            tenders = await scrape_page(page, i)
            await save_to_db(tenders)

        await browser.close()
    logging.info("✅ Done scraping.")

if __name__ == "__main__":
    asyncio.run(main())
