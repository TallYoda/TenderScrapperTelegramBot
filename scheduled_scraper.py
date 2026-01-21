import argparse
import asyncio
import logging
from datetime import timedelta

from scraper_lib import scrape_pages


def parse_args():
    parser = argparse.ArgumentParser(description="Run scheduled tender scraping.")
    parser.add_argument("--pages", type=int, default=5, help="Number of pages to scrape each run.")
    parser.add_argument(
        "--interval-hours",
        type=int,
        default=24,
        help="Hours between scraping runs."
    )
    parser.add_argument(
        "--no-details",
        action="store_true",
        help="Skip detail-page scraping."
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single scrape and exit."
    )
    return parser.parse_args()


async def run_loop(pages, interval_hours, scrape_details):
    while True:
        await scrape_pages(pages, scrape_details=scrape_details)
        await asyncio.sleep(timedelta(hours=interval_hours).total_seconds())


async def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    if args.once:
        await scrape_pages(args.pages, scrape_details=not args.no_details)
    else:
        await run_loop(args.pages, args.interval_hours, scrape_details=not args.no_details)


if __name__ == "__main__":
    asyncio.run(main())

