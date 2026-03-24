"""Generate a summary report from the activity log."""

import os
import csv
from collections import defaultdict

from config import ACTIVITY_LOG


def run():
    if not os.path.exists(ACTIVITY_LOG):
        print("No activity_log.csv found. Run `python run.py outreach` first.")
        return

    with open(ACTIVITY_LOG, newline="") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("No activity logged yet.")
        return

    buckets: dict[str, list] = defaultdict(list)
    for row in rows:
        buckets[row["result"]].append(row)

    def fmt(r):
        url = r.get("linkedin_url", "")
        suffix = f"  {url}" if url else ""
        return f"  {r['email']}{suffix}  [{r['timestamp']}]"

    def print_bucket(label, items):
        print(f"{label} ({len(items)}):")
        print("\n".join(fmt(r) for r in items) if items else "  None")
        print()

    print("=" * 50)
    print("LINKEDIN AUTOMATION REPORT")
    print("=" * 50)
    print(f"Total entries: {len(rows)}\n")

    print_bucket("Invites Sent", buckets.get("invite_sent", []))
    print_bucket("Accepted + Follow-up DM Sent", buckets.get("accepted", []))
    print_bucket("Messaged — already connected", buckets.get("messaged", []))
    print_bucket("Ignored (invite expired or declined)", [
        r for k, v in buckets.items() if k.startswith("ignored") for r in v
    ])
    print_bucket("Still Pending", buckets.get("pending", []))

    errors = {k: v for k, v in buckets.items() if k.startswith("error")}
    error_count = sum(len(v) for v in errors.values())
    print(f"Errors ({error_count}):")
    for result, items in errors.items():
        print(f"  [{result}]")
        for r in items:
            print(f"  {fmt(r)}")
    if not errors:
        print("  None")

    print("=" * 50)
