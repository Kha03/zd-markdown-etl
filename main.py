from scraper import scrape_zendesk_articles
from gemini_store import sync_store


def main():
    print("========================================")
    print("OPTIBOT DAILY ETL JOB")
    print("========================================")

    # 1. Re-scrape Zendesk
    scraped_count = scrape_zendesk_articles()

    print(
        f"\n[SCRAPER] Articles scraped: "
        f"{scraped_count}"
    )

    # 2. Sync only added / updated articles
    result = sync_store()

    print("\n========================================")
    print("JOB SUMMARY")
    print("========================================")
    print(f"Scraped : {scraped_count}")
    print(f"Added   : {result['added']}")
    print(f"Updated : {result['updated']}")
    print(f"Skipped : {result['skipped']}")
    print("========================================")

    print("\nJob completed successfully.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())