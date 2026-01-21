import asyncio
import json
import os
import logging
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

INPUT_JSON = "tenders.json"  # contains tender urls
OUTPUT_JSON = "tender_details.json"

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

async def scrape_detail_page(playwright, tender):
    browser = await playwright.chromium.launch(headless=True)
    page = await browser.new_page()
    url = tender["url"]
    tender_id = tender["tender_id"]
    logging.info(f"Scraping detail page: {url}")

    try:
        await page.goto(url, timeout=60000)
        await page.wait_for_selector("div.ant-tree-list", timeout=15000)
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        # Extract title
        title_tag = soup.select_one("h1.text-xl.font-semibold")
        title = title_tag.get_text(strip=True) if title_tag else None

        # Extract description
        paragraphs = soup.find_all("p")
        description = "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))

        # Extract "Filed under"
        filed_under = None
        filed_under_container = soup.select_one("div.ant-tree-list-holder-inner")

        if filed_under_container:
            #category_links = filed_under_container.select("span.ant-tree-title a")
            #categories = [link.get_text(strip=True) for link in category_links if link.get_text(strip=True)]
            categories = list({a.get_text(strip=True) for a in soup.select("span.ant-tree-title a")})

            filed_under = ", ".join(categories) if categories else None

        # Extract "Filed under"
        #filed_under_div = soup.select_one("div.ant-tree-list")
        #filed_under = None
        #if filed_under_div:
            #category_tags = filed_under_div.find_all("span")
            #filed_under = ", ".join(span.get_text(strip=True) for span in category_tags if span.get_text(strip=True))

        return {
            "tender_id": tender_id,
            "url": url,
            "title": title,
            "description": description,
            "filed_under": filed_under
        }

    except Exception as e:
        logging.warning(f"❌ Failed to scrape {url}: {e}")
        return None
    finally:
        await page.close()
        await browser.close()


async def main():
    os.makedirs("output", exist_ok=True)
    with open(INPUT_JSON, "r", encoding="utf-8") as f:
        tenders = json.load(f)

    scraped_data = []

    async with async_playwright() as p:
        for tender in tenders:
            result = await scrape_detail_page(p, tender)
            if result:
                scraped_data.append(result)

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(scraped_data, f, indent=2, ensure_ascii=False)

    logging.info(f"✅ Scraped {len(scraped_data)} tender details saved to {OUTPUT_JSON}")

if __name__ == "__main__":
    asyncio.run(main())
