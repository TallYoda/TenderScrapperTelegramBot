import html
import json
import logging
import re
from datetime import datetime, timedelta

import psycopg
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackContext, CallbackQueryHandler
from config_loader import get_required_config

# ---------- CONFIG ----------
CONFIG = get_required_config(["DB_URL", "TELEGRAM_TOKEN"])
DB_URL = CONFIG["DB_URL"]
TELEGRAM_TOKEN = CONFIG["TELEGRAM_TOKEN"]

# ---------- LOGGING ----------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def _truncate(text, max_len=1800):
    if text and len(text) > max_len:
        return text[: max_len - 3].rstrip() + "..."
    return text

def _normalize_date_text(value):
    if not value:
        return ""
    cleaned = value.replace(",", " ")
    cleaned = cleaned.replace("(", " ").replace(")", " ")
    cleaned = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _extract_date_candidate(value):
    cleaned = _normalize_date_text(value)
    if not cleaned:
        return ""
    patterns = [
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}\s+\d{4}",
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}\s+\d{4}",
        r"\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}",
        r"\d{1,2}\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}",
        r"\d{4}-\d{2}-\d{2}",
        r"\d{1,2}/\d{1,2}/\d{4}"
    ]
    for pattern in patterns:
        match = re.search(pattern, cleaned)
        if match:
            return match.group(0)
    return cleaned

def _parse_date(value):
    cleaned = _extract_date_candidate(value)
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

def get_last_scrape_status():
    conn = psycopg.connect(DB_URL, sslmode="require")
    cur = conn.cursor()
    cur.execute("SELECT run_at, pages_scraped, tenders_saved FROM scrape_status ORDER BY run_at DESC LIMIT 1;")
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row

def get_tenders_since(days_count):
    cutoff_date = datetime.utcnow().date() - timedelta(days=max(days_count - 1, 0))
    conn = psycopg.connect(DB_URL, sslmode="require")
    cur = conn.cursor()
    cur.execute("SELECT id, title, bid_closing_date, bid_opening_date, published_on, url FROM tenders1;")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    results = []
    for row in rows:
        published_on = row[4]
        published_date = _parse_date(published_on)
        if published_date and published_date >= cutoff_date:
            results.append({
                "id": row[0],
                "title": row[1],
                "bid_closing_date": row[2],
                "bid_opening_date": row[3],
                "published_on": published_on,
                "url": row[5]
            })
    return results


def _safe_json_loads(value):
    if not value:
        return {}
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {}


def get_tender_by_id(tender_id):
    conn = psycopg.connect(DB_URL, sslmode="require")
    cur = conn.cursor()
    cur.execute(
        "SELECT id, title, bid_closing_date, bid_opening_date, published_on, url FROM tenders1 WHERE id = %s;",
        (tender_id,)
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return None
    return {
        "id": row[0],
        "title": row[1],
        "bid_closing_date": row[2],
        "bid_opening_date": row[3],
        "published_on": row[4],
        "url": row[5]
    }


def get_tender_details(tender_id):
    conn = psycopg.connect(DB_URL, sslmode="require")
    cur = conn.cursor()
    cur.execute("""
        SELECT title, description, filed_under, company, metadata_json, extra_fields_json
        FROM tender_details
        WHERE tender_id = %s;
    """, (tender_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return None
    return {
        "title": row[0],
        "description": row[1],
        "filed_under": row[2],
        "company": row[3],
        "metadata": _safe_json_loads(row[4]),
        "extra_fields": _safe_json_loads(row[5])
    }


def format_tender_details(tender, details):
    if not details:
        return (
            "ℹ️ Details are not available yet.\n"
            "Please try again later after the scheduled scraper runs."
        )
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
    try:
        tender = tender_cache.get(tender_id) or get_tender_by_id(tender_id)
        if not tender:
            await query.message.reply_text("Tender not found.")
            return
        details = get_tender_details(tender_id)
    except Exception as exc:
        logging.error("DB query failed: %s", exc)
        await query.message.reply_text("Database is not ready yet. Please try later.")
        return

    message = format_tender_details(tender, details)
    await query.message.reply_text(message, parse_mode="HTML")

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

    await query.message.reply_text("🔎 Fetching tenders from the database...")
    try:
        tenders = get_tenders_since(days_count)
    except Exception as exc:
        logging.error("DB query failed: %s", exc)
        await query.message.reply_text("Database is not ready yet. Please try later.")
        return
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

async def handle_status(update: Update, context: CallbackContext):
    try:
        status = get_last_scrape_status()
    except Exception as exc:
        logging.error("DB query failed: %s", exc)
        await update.message.reply_text("Database is not ready yet. Please try later.")
        return
    if not status:
        await update.message.reply_text("No scraping runs recorded yet.")
        return
    run_at, pages_scraped, tenders_saved = status
    text = (
        "📊 <b>Scrape Status</b>\n"
        f"🕒 <b>Last run</b>: {run_at}\n"
        f"📄 <b>Pages scraped</b>: {pages_scraped}\n"
        f"✅ <b>New tenders saved</b>: {tenders_saved}"
    )
    await update.message.reply_text(text, parse_mode="HTML")

# ---------- MAIN ----------
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", handle_status))
    app.add_handler(CallbackQueryHandler(handle_range, pattern=r"^range:"))
    app.add_handler(CallbackQueryHandler(handle_details, pattern=r"^details:"))

    print("🤖 Bot is running...")
    app.run_polling()
