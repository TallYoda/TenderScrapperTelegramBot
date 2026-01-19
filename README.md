# TenderScrapperTelegramBot (Practice)

This repository is **practice code** for a Telegram bot that scrapes publicly available tender listings
from `2merkato.com`, stores them in a database, and displays them in chat. It is not production-hardened.

## What It Does

- Scrapes tender listings from the public free tenders page.
- Stores scraped tenders in a PostgreSQL database.
- Lets users pick a date range (today, last 2 days, last 7 days).
- Displays tender summaries in Telegram.
- Fetches and formats detail pages on demand.
- Exposes a `/status` command that reports the most recent scrape run.

## Libraries Used

- `python-telegram-bot` — Telegram bot framework.
- `playwright` — headless browser automation for scraping.
- `beautifulsoup4` — HTML parsing and data extraction.
- `psycopg2` — PostgreSQL database access.
- Standard library modules like `asyncio`, `datetime`, `logging`, `re`.

## Methods/Approach

- Listing pages are scraped from `https://tender.2merkato.com/tenders/free?page={}`.
- An initial scrape runs on startup (first 5 pages), then a daily scrape runs after that.
- Results are filtered by published date based on the selected time range.
- Detail pages are scraped when a user taps “View Details”.
- Data is formatted with HTML and emojis for readability inside Telegram.
- Scrape progress is stored in a `scrape_status` table in the database.

## Notes

- This is for learning/practice only.
- The bot requires `DB_URL` and `TELEGRAM_TOKEN` in `config.json` (ignored by git).

