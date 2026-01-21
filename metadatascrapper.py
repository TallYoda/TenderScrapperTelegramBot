import asyncio
import json
import logging
import os
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

INPUT_FILE = "tenders.json"
OUTPUT_FILE = "tender_details_enriched1.json"
BASE_URL = "https://tender.2merkato.com"

# Mapping for metadata labels to JSON keys
detail_fields = {
    "bid closing date": "bid_closing_date",
    "bid opening date": "bid_opening_date",
    "published on": "published_on",
    "posted": "posted",
    "bid document price": "bid_document_price",
    "bid bond": "bid_bond",
    "region": "region",
    "bidding": "bidding_type"
}

async def scrape_tender_detail(page, url):
    try:
        await page.goto(url, timeout=60000)
        await page.wait_for_selector("div.ant-tree-list", timeout=15000)
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        # Extract tender_id from URL
        tender_id = urlparse(url).path.split("/")[-1]

        # Extract title
        title_tag = soup.select_one("h1.text.xl.font-semibold")
        title = title_tag.get_text(strip=True) if title_tag else None

        # Extract description
        desc_tag = soup.select_one("div.overflow-x-auto")
        paragraphs = desc_tag.find_all("p") if desc_tag else []
        description = "\n".join([p.get_text(strip=True) for p in paragraphs]) if paragraphs else None

        # Extract "filed under" categories
        category_links = soup.select("div.ant-tree-title a")
        filed_under = ", ".join(sorted(set(a.get_text(strip=True) for a in category_links))) if category_links else None

        # Extract metadata fields
        metadata = {}
        info_rows = soup.select("div.flex.gap-x-4.gap-y-0.p-2.flex-wrap")
        for row in info_rows:
            label_div = row.select_one("div.font-medium")
            if label_div:
                label_text = label_div.get_text(strip=True).rstrip(":").lower()
                if label_text == "bidding_type":
                    continue
                value_div = label_div.find_next_sibling("div")
                value_text = value_div.get_text(strip=True) if value_div else ""
                key = detail_fields.get(label_text)
                if key:
                    metadata[key] = value_text

        return {
                "tender_id": tender_id,
                "url": url,
                "title": title,
                "description": description,
                "filed_under": filed_under,
                **metadata
            }

    except Exception as e:
        logging.warning(f"⚠️ Failed to scrape detail for {url}: {e}")
        return None

async def scrape_all_tender_details():
    os.makedirs("output", exist_ok=True)

    # Load input JSON with tender URLs
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        tenders = json.load(f)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        results = []
        for i, tender in enumerate(tenders):
            url = tender.get("url")
            if not url:
                continue
            logging.info(f"🔍 Scraping ({i+1}/{len(tenders)}): {url}")
            data = await scrape_tender_detail(page, url)
            if data:
                results.append(data)

        await browser.close()

    # Save enriched data
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    logging.info(f"✅ Saved {len(results)} enriched tender details to {OUTPUT_FILE}")

# Run the scraper
asyncio.run(scrape_all_tender_details())
