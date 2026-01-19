import html
import logging
import re
from datetime import datetime, timedelta

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackContext, CallbackQueryHandler
from config_loader import get_required_config

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

# ---------- CONFIG ----------
CONFIG = get_required_config(["TELEGRAM_TOKEN"])
TELEGRAM_TOKEN = CONFIG["TELEGRAM_TOKEN"]
BASE_URL = "https://tender.2merkato.com/tenders/free?page={}"
MAX_PAGES = 50

# ---------- LOGGING ----------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def _clean_text(value):
    return " ".join(value.split()) if value else ""

def _truncate(text, max_len=1800):
    if text and len(text) > max_len:
        return text[: max_len - 3].rstrip() + "..."
    return text

def _normalize_date_text(value):
    if not value:
        return ""
    cleaned = value.replace(",", " ")
    cleaned = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned

def _parse_date(value):
    cleaned = _normalize_date_text(value)
    if not cleaned:
        return None
    lowered = cleaned.lower()
    if lowered == "today":
        return datetime.utcnow().date()
    if lowered == "yesterday":
        return datetime.utcnow().date() - timedelta(days=1)
    formats = [
        "%b %d %Y",
        "%B %d %Y",
        "%d %b %Y",
        "%d %B %Y",
        "%Y-%m-%d",
        "%d/%m/%Y"
    ]
    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None

async def scrape_tenders_since(days_count):
    cutoff_date = datetime.utcnow().date() - timedelta(days=max(days_count - 1, 0))
    results = []
    seen_ids = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            for page_num in range(1, MAX_PAGES + 1):
                url = BASE_URL.format(page_num)
                logging.info("Scraping page %s -> %s", page_num, url)
                await page.goto(url, timeout=60000)
                await page.wait_for_selector("h3.font-medium.text-lg.tracking-wide.leading-6 a", timeout=15000)
                html_content = await page.content()
                soup = BeautifulSoup(html_content, "html.parser")
                h3_tags = soup.select("h3.font-medium.text-lg.tracking-wide.leading-6")
                if not h3_tags:
                    break

                page_has_newer = False
                page_has_any_published = False
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
                        if tender_id in seen_ids:
                            continue
                        seen_ids.add(tender_id)

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

                        published_date = _parse_date(published_on)
                        if published_date:
                            page_has_any_published = True
                        if published_date and published_date >= cutoff_date:
                            page_has_newer = True
                            results.append({
                                "id": tender_id,
                                "title": title,
                                "url": full_url,
                                "bid_closing_date": closing_date,
                                "bid_opening_date": opening_date,
                                "published_on": published_on
                            })
                    except Exception as exc:
                        logging.warning("Skipping tender: %s", exc)

                if page_has_any_published and not page_has_newer and results:
                    break
        finally:
            await page.close()
            await browser.close()

    return results

async def scrape_tender_details(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
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
            description = _clean_text(description)

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
            await browser.close()

def format_tender_details(tender, details):
    title = details.get("title") or tender.get("title") or "Tender Details"
    title_html = html.escape(title)
    closing = html.escape(tender.get("bid_closing_date") or "N/A")
    opening = html.escape(tender.get("bid_opening_date") or "N/A")
    filed_under = html.escape(details.get("filed_under") or "N/A")
    company = html.escape(details.get("company") or "N/A")
    metadata = details.get("metadata") or {}
    extra_fields = details.get("extra_fields") or {}
    description = html.escape(details.get("description") or "No description available.")

    lines = [
        f"📌 <b>{title_html}</b>",
        f"🗓 <b>Closing</b>: {closing}",
        f"🗓 <b>Opening</b>: {opening}",
        f"🏢 <b>Company</b>: {company}",
        f"🗂 <b>Filed under</b>: {filed_under}"
    ]

    def add_field(label, key):
        value = metadata.get(key)
        if value:
            lines.append(f"{label}: {html.escape(value)}")

    add_field("📅 <b>Published</b>", "published_on")
    add_field("🗓 <b>Posted</b>", "posted")
    add_field("💵 <b>Bid document price</b>", "bid_document_price")
    add_field("💰 <b>Bid bond</b>", "bid_bond")
    add_field("📍 <b>Region</b>", "region")
    add_field("🧾 <b>Bidding</b>", "bidding_type")

    for label in sorted(extra_fields.keys()):
        value = extra_fields[label]
        if value:
            lines.append(f"• <b>{html.escape(label)}</b>: {html.escape(value)}")

    message = "\n".join(lines) + "\n\n" + _truncate(description, 1800)
    if len(message) > 4000:
        message = "\n".join(lines) + "\n\n" + _truncate(description, 1200)
    if len(message) > 4000:
        trimmed_lines = [line for line in lines if not line.startswith("• ")]
        message = "\n".join(trimmed_lines) + "\n\n" + _truncate(description, 1200)
    return message

# ---------- TELEGRAM HANDLERS ----------
async def start(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    welcome = (
        "👋 <b>Welcome to Chereta 4 Us!</b>\n\n"
        "🤖 I’m a Telegram bot that scrapes the most current freely available "
        "tender info from <b>2merkato.com</b>.\n\n"
        "👇 Choose how recent you want the tenders:"
    )
    keyboard = [
        [InlineKeyboardButton("🆕 Tenders Posted Today", callback_data="range:1")],
        [InlineKeyboardButton("🗓 Tenders Posted The last two days", callback_data="range:2")],
        [InlineKeyboardButton("📅 Tenders Posted in the Last week", callback_data="range:7")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=chat_id, text=welcome, parse_mode="HTML", reply_markup=reply_markup)

async def handle_details(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    if not query.data or not query.data.startswith("details:"):
        return

    tender_id = query.data.split(":", 1)[1]
    tender_cache = context.bot_data.get("tender_cache", {})
    tender = tender_cache.get(tender_id)
    if not tender:
        await query.message.reply_text("Tender not found. Please request tenders again.")
        return

    await query.message.reply_text("Fetching details...")
    try:
        details = await scrape_tender_details(tender["url"])
        message = format_tender_details(tender, details)
        await query.message.reply_text(message, parse_mode="HTML")
    except Exception as exc:
        await query.message.reply_text(f"Failed to fetch details: {exc}")

async def handle_range(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    if not query.data or not query.data.startswith("range:"):
        return

    try:
        days_count = int(query.data.split(":", 1)[1])
    except ValueError:
        await query.message.reply_text("Invalid selection.")
        return

    await query.message.reply_text("⏳ Scraping tenders, please wait...")
    tenders = await scrape_tenders_since(days_count)
    if not tenders:
        await query.message.reply_text("No tenders found for that period.")
        return

    tender_cache = context.bot_data.setdefault("tender_cache", {})
    for tender in tenders:
        tender_cache[tender["id"]] = tender
        text = (
            f"📌 <b>{html.escape(tender['title'])}</b>\n"
            f"🗓 <b>Closing</b>: {html.escape(tender.get('bid_closing_date') or 'N/A')}\n"
            f"🗓 <b>Opening</b>: {html.escape(tender.get('bid_opening_date') or 'N/A')}\n"
            f"📅 <b>Published</b>: {html.escape(tender.get('published_on') or 'N/A')}"
        )
        keyboard = [
            [InlineKeyboardButton("View Details", callback_data=f"details:{tender['id']}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text(text=text, parse_mode="HTML", reply_markup=reply_markup)

# ---------- MAIN ----------
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_range, pattern=r"^range:"))
    app.add_handler(CallbackQueryHandler(handle_details, pattern=r"^details:"))

    print("🤖 Bot is running...")
    app.run_polling()
