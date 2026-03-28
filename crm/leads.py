"""
Lead and activity data access — delegates to crm/db.py (SQLite).
Workflows import from here; they don't need to know about the underlying storage.
"""

from crm import db


def load_processed_emails() -> set[str]:
    return db.load_processed_emails()


def load_invite_sent_leads() -> dict[str, str]:
    return db.load_invite_sent_leads()


def load_invite_sent_leads_with_names() -> dict[str, dict]:
    return db.load_invite_sent_leads_with_names()


def count_processed_today() -> int:
    return db.count_processed_today()


def count_connections_this_week() -> int:
    return db.count_connections_this_week()


def reset_today():
    db.reset_today()


def log_activity(email: str, result: str, linkedin_url: str = ""):
    """Log a LinkedIn action. Upserts the lead if not yet in DB, then appends to activity log."""
    db.init_db()
    db.upsert_lead(email, linkedin_url=linkedin_url or None)
    db.log_activity(email, result)


def get_first_name(email: str) -> str:
    return db.get_first_name(email)
