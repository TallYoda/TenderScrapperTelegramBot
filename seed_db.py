import argparse
import asyncio
import logging

from scraper_lib import scrape_pages


def parse_args():
    parser = argparse.ArgumentParser(description="Seed the database with tender data.")
    parser.add_argument("--pages", type=int, default=5, help="Number of pages to scrape.")
    parser.add_argument(
        "--no-details",
        action="store_true",
        help="Skip detail-page scraping."
    )
    return parser.parse_args()


async def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    await scrape_pages(args.pages, scrape_details=not args.no_details)


if __name__ == "__main__":
    asyncio.run(main())

