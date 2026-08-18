from scraper import scrape_zendesk_articles
from gemini_store import sync_store
import os
def check_manifest():
    path = "/app/state/manifest.json"

    print("\n========================================")
    print("VOLUME / MANIFEST CHECK")
    print("========================================")
    print(f"Path: {path}")

    if not os.path.exists(path):
        print("manifest.json: NOT FOUND")

        if os.path.exists("/app/state"):
            print("Directory contents:")
            for name in os.listdir("/app/state"):
                print(f"  - {name}")
        else:
            print("/app/state does not exist")

        return

    size = os.path.getsize(path)

    print("manifest.json: EXISTS")
    print(f"Size: {size} bytes")

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    print(f"Manifest entries: {content.count('\"file\":')}")
    print("========================================")

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
    check_manifest()

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