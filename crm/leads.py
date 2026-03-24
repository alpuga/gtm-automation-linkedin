"""Local activity log — CSV-based record of all LinkedIn actions taken."""

import os
import csv
from datetime import datetime

from config import ACTIVITY_LOG

FIELDNAMES = ["email", "linkedin_url", "result", "timestamp"]


def load_processed_emails() -> set[str]:
    """Return set of emails already processed in any previous run."""
    if not os.path.exists(ACTIVITY_LOG):
        return set()
    with open(ACTIVITY_LOG, newline="") as f:
        return {row["email"] for row in csv.DictReader(f)}


def load_invite_sent_leads() -> dict[str, str]:
    """Return {email: linkedin_url} for leads whose latest logged result is 'invite_sent'."""
    if not os.path.exists(ACTIVITY_LOG):
        return {}
    latest: dict[str, dict] = {}
    with open(ACTIVITY_LOG, newline="") as f:
        for row in csv.DictReader(f):
            latest[row["email"]] = row  # last row per email wins
    return {
        email: row["linkedin_url"]
        for email, row in latest.items()
        if row.get("result") == "invite_sent"
    }


def count_processed_today() -> int:
    """Count how many leads were processed today."""
    if not os.path.exists(ACTIVITY_LOG):
        return 0
    today = datetime.now().date().isoformat()
    with open(ACTIVITY_LOG, newline="") as f:
        return sum(1 for row in csv.DictReader(f) if row.get("timestamp", "").startswith(today))


def count_connections_this_week() -> int:
    """Count invite_sent entries in the last 7 days."""
    if not os.path.exists(ACTIVITY_LOG):
        return 0
    cutoff = datetime.now().timestamp() - 7 * 24 * 3600
    count = 0
    with open(ACTIVITY_LOG, newline="") as f:
        for row in csv.DictReader(f):
            if row.get("result") == "invite_sent":
                try:
                    if datetime.fromisoformat(row["timestamp"]).timestamp() >= cutoff:
                        count += 1
                except (ValueError, KeyError):
                    pass
    return count


def reset_today():
    """Remove today's entries from the activity log to reset the daily limit."""
    if not os.path.exists(ACTIVITY_LOG):
        print("No activity_log.csv found — nothing to reset.")
        return
    today = datetime.now().date().isoformat()
    with open(ACTIVITY_LOG, newline="") as f:
        rows = list(csv.DictReader(f))
    kept = [r for r in rows if not r.get("timestamp", "").startswith(today)]
    removed = len(rows) - len(kept)
    with open(ACTIVITY_LOG, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(kept)
    print(f"Removed {removed} entry/entries from today. Daily limit reset.")


def log_activity(email: str, result: str, linkedin_url: str = ""):
    """Append a LinkedIn action to the activity log."""
    os.makedirs("data", exist_ok=True)
    write_header = not os.path.exists(ACTIVITY_LOG)
    with open(ACTIVITY_LOG, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if write_header:
            writer.writeheader()
        writer.writerow({
            "email": email,
            "linkedin_url": linkedin_url,
            "result": result,
            "timestamp": datetime.now().isoformat(),
        })
