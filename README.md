# TenderScrapperTelegramBot (Practice)

This repository is **practice code** for a Telegram bot that scrapes publicly available tender listings
from `2merkato.com`, stores them in a database, and displays them in chat. It is not production-hardened.

## What It Does

- Scrapes tender listings from the public free tenders page.
- Stores scraped tenders in a PostgreSQL database.
- Lets users pick a date range (today, last 2 days, last 7 days).
- Displays tender summaries in Telegram.
- Displays tender details that were scraped by the scheduled scraper.
- Exposes a `/status` command that reports the most recent scrape run.

## Libraries Used

- `python-telegram-bot` — Telegram bot framework.
- `playwright` — headless browser automation for scraping.
- `beautifulsoup4` — HTML parsing and data extraction.
- `psycopg` — PostgreSQL database access.
- Standard library modules like `asyncio`, `datetime`, `logging`, `re`.

## Methods/Approach

- Listing pages are scraped from `https://tender.2merkato.com/tenders/free?page={}`.
- Run `seed_db.py` locally to populate the database (defaults to 5 pages).
- Run `scheduled_scraper.py` separately to keep the DB fresh.
- Results are filtered by published date based on the selected time range.
- Detail pages are scraped by the scheduled scraper and stored in `tender_details`.
- Data is formatted with HTML and emojis for readability inside Telegram.
- Scrape progress is stored in a `scrape_status` table in the database.

## Notes

- This is for learning/practice only.
- The bot expects `DB_URL` and `TELEGRAM_TOKEN` as environment variables.
- You can also use `config.json` for local runs (ignored by git).

