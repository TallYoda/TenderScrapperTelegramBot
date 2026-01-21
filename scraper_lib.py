import json
import logging
from datetime import datetime

import psycopg
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from config_loader import get_required_config

BASE_URL = "https://tender.2merkato.com/tenders/free?page={}"

DETAIL_FIELDS = {
    "bid closing date": "bid_closing_date",
    "bid opening date": "bid_opening_date",
    "published on": "published_on",
    "posted": "posted",
    "bid document price": "bid_document_price",
    "bid bond": "bid_bond",
    "region": "region",
    "bidding": "bidding_type"
}


def _get_db_url():
    config = get_required_config(["DB_URL"])
    return config["DB_URL"]


def init_db():
    conn = psycopg.connect(_get_db_url(), sslmode="require")
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
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tender_details (
            tender_id TEXT PRIMARY KEY,
            title TEXT,
            description TEXT,
            filed_under TEXT,
            company TEXT,
            metadata_json TEXT,
            extra_fields_json TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS scrape_status (
            id SERIAL PRIMARY KEY,
            run_at TIMESTAMP NOT NULL,
            pages_scraped INTEGER NOT NULL,
            tenders_saved INTEGER NOT NULL
        )
    """)
    conn.commit()
    cur.close()
    conn.close()


def load_existing_ids():
    conn = psycopg.connect(_get_db_url(), sslmode="require")
    cur = conn.cursor()
    cur.execute("SELECT id FROM tenders1;")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return set(row[0] for row in rows)


def insert_tender(tender):
    conn = psycopg.connect(_get_db_url(), sslmode="require")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO tenders1 (id, title, url, bid_closing_date, bid_opening_date, published_on)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
    """, (
        tender["id"],
        tender["title"],
        tender["url"],
        tender.get("bid_closing_date"),
        tender.get("bid_opening_date"),
        tender.get("published_on")
    ))
    inserted = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    return inserted


def upsert_tender_details(tender_id, details):
    conn = psycopg.connect(_get_db_url(), sslmode="require")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO tender_details (
            tender_id,
            title,
            description,
            filed_under,
            company,
            metadata_json,
            extra_fields_json
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (tender_id) DO UPDATE SET
            title = EXCLUDED.title,
            description = EXCLUDED.description,
            filed_under = EXCLUDED.filed_under,
            company = EXCLUDED.company,
            metadata_json = EXCLUDED.metadata_json,
            extra_fields_json = EXCLUDED.extra_fields_json
    """, (
        tender_id,
        details.get("title"),
        details.get("description"),
        details.get("filed_under"),
        details.get("company"),
        json.dumps(details.get("metadata") or {}),
        json.dumps(details.get("extra_fields") or {})
    ))
    conn.commit()
    cur.close()
    conn.close()


def record_scrape_status(pages_scraped, tenders_saved):
    conn = psycopg.connect(_get_db_url(), sslmode="require")
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO scrape_status (run_at, pages_scraped, tenders_saved) VALUES (%s, %s, %s);",
        (datetime.utcnow(), pages_scraped, tenders_saved)
    )
    conn.commit()
    cur.close()
    conn.close()


async def scrape_detail_page(browser, url):
    page = await browser.new_page()
    try:
        await page.goto(url, timeout=60000)
        await page.wait_for_selector("div.ant-tree-list", timeout=15000)
        html_content = await page.content()
        soup = BeautifulSoup(html_content, "html.parser")

        title_tag = soup.select_one("h1.text-xl.font-semibold")
        title = title_tag.get_text(strip=True) if title_tag else None

        paragraphs = soup.find_all("p")
        description = "\n".join(
            p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)
        )

        categories = list({a.get_text(strip=True) for a in soup.select("span.ant-tree-title a")})
        filed_under = ", ".join(categories) if categories else None

        company_tag = soup.select_one("h3.text-lg.font-medium.m-0.underline.text-blue-600 a")
        company = company_tag.get_text(strip=True) if company_tag else None

        metadata = {}
        extra_fields = {}
        info_rows = soup.select("div.flex.gap-x-4.gap-y-0.p-2.flex-wrap")
        for row in info_rows:
            label_div = row.select_one("div.font-medium")
            if not label_div:
                continue
            label_text = label_div.get_text(strip=True).rstrip(":")
            value_div = label_div.find_next_sibling("div")
            value_text = value_div.get_text(strip=True) if value_div else ""
            if not value_text:
                continue
            label_key = label_text.lower()
            key = DETAIL_FIELDS.get(label_key)
            if key:
                metadata[key] = value_text
            else:
                extra_fields[label_text] = value_text

        return {
            "title": title,
            "description": description,
            "filed_under": filed_under,
            "company": company,
            "metadata": metadata,
            "extra_fields": extra_fields
        }
    finally:
        await page.close()


async def scrape_pages(pages_to_scrape, scrape_details=True):
    init_db()
    existing_ids = load_existing_ids()
    tenders_saved = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            for page_num in range(1, pages_to_scrape + 1):
                url = BASE_URL.format(page_num)
                logging.info("Scraping page %s -> %s", page_num, url)
                await page.goto(url, timeout=60000)
                await page.wait_for_selector("h3.font-medium.text-lg.tracking-wide.leading-6 a", timeout=15000)
                html_content = await page.content()
                soup = BeautifulSoup(html_content, "html.parser")
                h3_tags = soup.select("h3.font-medium.text-lg.tracking-wide.leading-6")

                for h3 in h3_tags:
                    try:
                        a_tag = h3.select_one("a")
                        if not a_tag:
                            continue
                        title = a_tag.get_text(strip=True)
                        href = a_tag.get("href", "").strip()
                        if not href:
                            continue
                        full_url = href if href.startswith("http") else "https://tender.2merkato.com" + href
                        tender_id = full_url.rstrip("/").split("/")[-1]
                        if tender_id in existing_ids:
                            continue

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
                            "id": tender_id,
                            "title": title,
                            "url": full_url,
                            "bid_closing_date": closing_date,
                            "bid_opening_date": opening_date,
                            "published_on": published_on
                        }
                        inserted = insert_tender(tender_data)
                        if inserted:
                            existing_ids.add(tender_id)
                            tenders_saved += 1
                            if scrape_details:
                                details = await scrape_detail_page(browser, full_url)
                                upsert_tender_details(tender_id, details)
                    except Exception as exc:
                        logging.warning("Skipping tender: %s", exc)
        finally:
            await page.close()
            await browser.close()

    record_scrape_status(pages_to_scrape, tenders_saved)
    return tenders_saved

