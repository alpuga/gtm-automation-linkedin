"""
SQLite data layer — single source of truth for leads and activity history.

Schema:
  leads        — one row per lead, current linkedin_status
  activity_log — append-only history of every LinkedIn action taken
"""

import os
import sqlite3
from datetime import datetime, timezone

from config import DB_FILE

VALID_STATUSES = {
    "not_contacted",
    "invite_sent",
    "pending",
    "accepted",
    "ignored",
    "messaged",
}


def get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create tables if they don't exist."""
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS leads (
                email           TEXT PRIMARY KEY,
                first_name      TEXT,
                last_name       TEXT,
                linkedin_url    TEXT,
                company         TEXT,
                source          TEXT,
                linkedin_status TEXT NOT NULL DEFAULT 'not_contacted',
                last_action_at  TEXT,
                created_at      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS activity_log (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                email     TEXT NOT NULL REFERENCES leads(email),
                result    TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_activity_email
                ON activity_log(email);
            CREATE INDEX IF NOT EXISTS idx_activity_timestamp
                ON activity_log(timestamp);
            CREATE INDEX IF NOT EXISTS idx_leads_status
                ON leads(linkedin_status);
        """)


def upsert_lead(
    email: str,
    first_name: str = None,
    last_name: str = None,
    linkedin_url: str = None,
    company: str = None,
    source: str = None,
):
    """Insert a new lead or update contact info if already exists. Never overwrites linkedin_status."""
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO leads (email, first_name, last_name, linkedin_url, company, source, created_at)
            VALUES (:email, :first_name, :last_name, :linkedin_url, :company, :source, :now)
            ON CONFLICT(email) DO UPDATE SET
                first_name   = COALESCE(:first_name, first_name),
                last_name    = COALESCE(:last_name, last_name),
                linkedin_url = COALESCE(:linkedin_url, linkedin_url),
                company      = COALESCE(:company, company),
                source       = COALESCE(:source, source)
        """, {
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "linkedin_url": linkedin_url,
            "company": company,
            "source": source,
            "now": now,
        })


def update_lead_status(email: str, status: str):
    """Update a lead's linkedin_status and last_action_at."""
    if status not in VALID_STATUSES:
        return
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute("""
            UPDATE leads SET linkedin_status = ?, last_action_at = ? WHERE email = ?
        """, (status, now, email))


def log_activity(email: str, result: str):
    """Append an action to the activity log and update lead status."""
    now = datetime.now(timezone.utc).isoformat()
    # Derive the canonical status from result
    status = _result_to_status(result)
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO activity_log (email, result, timestamp) VALUES (?, ?, ?)
        """, (email, result, now))
        if status:
            conn.execute("""
                UPDATE leads SET linkedin_status = ?, last_action_at = ? WHERE email = ?
            """, (status, now, email))


def load_invite_sent_leads() -> dict[str, str]:
    """
    Return {email: linkedin_url} for leads still awaiting a response (invite_sent or pending),
    where the last action was at least MIN_DM_WAIT_DAYS ago.
    """
    from config import MIN_DM_WAIT_DAYS
    init_db()
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT email, linkedin_url FROM leads
            WHERE linkedin_status IN ('invite_sent', 'pending')
            AND linkedin_url IS NOT NULL AND linkedin_url != ''
            AND (last_action_at IS NULL OR last_action_at <= datetime('now', :wait))
            ORDER BY last_action_at ASC
        """, {"wait": f"-{MIN_DM_WAIT_DAYS} days"}).fetchall()
    return {row["email"]: row["linkedin_url"] for row in rows}


def load_processed_emails() -> set[str]:
    """Return emails that have had a LinkedIn action taken (not just synced from CRM)."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT email FROM leads WHERE linkedin_status != 'not_contacted'
        """).fetchall()
    return {row["email"] for row in rows}


def count_processed_today() -> int:
    """Count activity log entries from today."""
    init_db()
    today = datetime.now().date().isoformat()
    with get_connection() as conn:
        row = conn.execute("""
            SELECT COUNT(*) as n FROM activity_log WHERE timestamp >= ?
        """, (today,)).fetchone()
    return row["n"] if row else 0


def count_connections_this_week() -> int:
    """Count invite_sent entries in the last 7 days."""
    init_db()
    with get_connection() as conn:
        row = conn.execute("""
            SELECT COUNT(*) as n FROM activity_log
            WHERE result = 'invite_sent'
            AND timestamp >= datetime('now', '-7 days')
        """).fetchone()
    return row["n"] if row else 0


def reset_today():
    """Remove today's activity log entries and revert affected lead statuses."""
    today = datetime.now().date().isoformat()
    with get_connection() as conn:
        affected = conn.execute("""
            SELECT DISTINCT email FROM activity_log WHERE timestamp >= ?
        """, (today,)).fetchall()
        conn.execute("DELETE FROM activity_log WHERE timestamp >= ?", (today,))
        for row in affected:
            # Revert to the last status before today
            prev = conn.execute("""
                SELECT result FROM activity_log
                WHERE email = ? ORDER BY timestamp DESC LIMIT 1
            """, (row["email"],)).fetchone()
            status = _result_to_status(prev["result"]) if prev else "not_contacted"
            conn.execute(
                "UPDATE leads SET linkedin_status = ? WHERE email = ?",
                (status or "not_contacted", row["email"])
            )
    print(f"Reset {len(affected)} lead(s) from today.")


def get_first_name(email: str) -> str:
    """Look up first name from the leads table."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT first_name FROM leads WHERE email = ?", (email,)
        ).fetchone()
    return (row["first_name"] or "there") if row else "there"


def _result_to_status(result: str) -> str | None:
    """Map an activity result string to a canonical linkedin_status."""
    if result == "invite_sent":
        return "invite_sent"
    if result == "accepted":
        return "accepted"
    if result == "messaged":
        return "messaged"
    if result == "pending":
        return "pending"
    if result and result.startswith("ignored"):
        return "ignored"
    return None
