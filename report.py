"""
Generate a summary report from processed_leads.csv.
"""

import os
import csv
from collections import defaultdict

PROCESSED_LOG = "processed_leads.csv"

CATEGORIES = {
    "connected": "Connected",
    "messaged": "Messaged",
}

def is_error(result: str) -> bool:
    return result.startswith("error")

def is_skipped(result: str) -> bool:
    return result.startswith("skipped")


def main():
    if not os.path.exists(PROCESSED_LOG):
        print("No processed_leads.csv found. Run main.py first.")
        return

    with open(PROCESSED_LOG, newline="") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("No leads logged yet.")
        return

    buckets = defaultdict(list)
    for row in rows:
        buckets[row["result"]].append(row)

    total = len(rows)
    connected = buckets.get("connected", [])
    messaged = buckets.get("messaged", [])
    errors = {k: v for k, v in buckets.items() if is_error(k)}
    skipped = {k: v for k, v in buckets.items() if is_skipped(k)}

    print("=" * 50)
    print("LINKEDIN AUTOMATION REPORT")
    print("=" * 50)
    print(f"Total leads processed: {total}\n")

    def fmt(r):
        url = r.get("linkedin_url", "")
        suffix = f"  {url}" if url else ""
        return f"  {r['email']}{suffix}  [{r['timestamp']}]"

    print(f"Connected ({len(connected)}):")
    if connected:
        for r in connected:
            print(fmt(r))
    else:
        print("  None")

    print(f"\nMessaged ({len(messaged)}):")
    if messaged:
        for r in messaged:
            print(fmt(r))
    else:
        print("  None")

    error_count = sum(len(v) for v in errors.values())
    print(f"\nErrors ({error_count}):")
    if errors:
        for result, leads in errors.items():
            print(f"  [{result}]")
            for r in leads:
                print(f"  {fmt(r)}")
    else:
        print("  None")

    skipped_count = sum(len(v) for v in skipped.items() if isinstance(v, list))
    print(f"\nSkipped ({skipped_count}):")
    if skipped:
        for result, leads in skipped.items():
            print(f"  [{result}]")
            for r in leads:
                print(f"  {fmt(r)}")
    else:
        print("  None")

    print("=" * 50)


if __name__ == "__main__":
    main()
