"""
One-time migration: import data/activity_log.csv into the SQLite database.

Safe to run multiple times — uses INSERT OR IGNORE to avoid duplicates.

Usage:
    poetry run python migrate_csv_to_db.py
"""

import csv
import os
from datetime import datetime, timezone

from crm import db
from config import ACTIVITY_LOG

STATUS_MAP = {
    "invite_sent": "invite_sent",
    "accepted":    "accepted",
    "messaged":    "messaged",
    "pending":     "pending",
}

def result_to_status(result: str) -> str:
    if result in STATUS_MAP:
        return STATUS_MAP[result]
    if result.startswith("ignored"):
        return "ignored"
    return "not_contacted"


def main():
    if not os.path.exists(ACTIVITY_LOG):
        print(f"No CSV found at {ACTIVITY_LOG} — nothing to migrate.")
        return

    db.init_db()

    with open(ACTIVITY_LOG, newline="") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("CSV is empty — nothing to migrate.")
        return

    # Build latest state per email from CSV
    latest: dict[str, dict] = {}
    for row in rows:
        latest[row["email"]] = row

    leads_inserted = 0
    leads_skipped = 0
    activities_inserted = 0

    from crm.db import get_connection

    with get_connection() as conn:
        for email, row in latest.items():
            linkedin_url = row.get("linkedin_url") or None
            status = result_to_status(row.get("result", ""))
            now = datetime.now(timezone.utc).isoformat()

            result = conn.execute("""
                INSERT OR IGNORE INTO leads
                    (email, linkedin_url, source, linkedin_status, created_at)
                VALUES (?, ?, 'csv_migration', ?, ?)
            """, (email, linkedin_url, status, now))

            if result.rowcount:
                leads_inserted += 1
            else:
                leads_skipped += 1

        for row in rows:
            email = row["email"]
            result_val = row.get("result", "")
            timestamp = row.get("timestamp", datetime.now(timezone.utc).isoformat())

            # Normalize timestamp to ISO format if needed
            try:
                datetime.fromisoformat(timestamp)
            except ValueError:
                timestamp = datetime.now(timezone.utc).isoformat()

            conn.execute("""
                INSERT INTO activity_log (email, result, timestamp)
                VALUES (?, ?, ?)
            """, (email, result_val, timestamp))
            activities_inserted += 1

    print(f"Migration complete.")
    print(f"  Leads inserted: {leads_inserted} (skipped {leads_skipped} already in DB)")
    print(f"  Activity log entries inserted: {activities_inserted}")


if __name__ == "__main__":
    main()
