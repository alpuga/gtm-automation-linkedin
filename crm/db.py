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
    "dm_sent",
    "inmail_sent",
    "engaged",
    "commented",
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
            CREATE TABLE IF NOT EXISTS lists (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT NOT NULL,
                sales_nav_url   TEXT NOT NULL UNIQUE,
                campaign        TEXT,
                created_at      TEXT NOT NULL,
                last_scraped_at TEXT
            );

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
        # Add new columns to existing DBs — silently skip if already present
        for col in ("title TEXT", "sales_nav_url TEXT", "campaign TEXT", "list_id INTEGER", "location TEXT", "bio TEXT", "headline TEXT", "score INTEGER", "score_reason TEXT", "persona TEXT"):
            try:
                conn.execute(f"ALTER TABLE leads ADD COLUMN {col}")
            except Exception:
                pass


def upsert_lead(
    email: str,
    first_name: str = None,
    last_name: str = None,
    linkedin_url: str = None,
    company: str = None,
    source: str = None,
    title: str = None,
    sales_nav_url: str = None,
    campaign: str = None,
    list_id: int = None,
    location: str = None,
    bio: str = None,
    headline: str = None,
):
    """Insert a new lead or update contact info if already exists. Never overwrites linkedin_status."""
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO leads (email, first_name, last_name, linkedin_url, company, source, title, sales_nav_url, campaign, list_id, location, bio, headline, created_at)
            VALUES (:email, :first_name, :last_name, :linkedin_url, :company, :source, :title, :sales_nav_url, :campaign, :list_id, :location, :bio, :headline, :now)
            ON CONFLICT(email) DO UPDATE SET
                first_name    = COALESCE(:first_name, first_name),
                last_name     = COALESCE(:last_name, last_name),
                linkedin_url  = COALESCE(:linkedin_url, linkedin_url),
                company       = COALESCE(:company, company),
                source        = COALESCE(:source, source),
                title         = COALESCE(:title, title),
                sales_nav_url = COALESCE(:sales_nav_url, sales_nav_url),
                campaign      = COALESCE(:campaign, campaign),
                list_id       = COALESCE(:list_id, list_id),
                location      = COALESCE(:location, location),
                bio           = COALESCE(:bio, bio),
                headline      = COALESCE(:headline, headline)
        """, {
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "linkedin_url": linkedin_url,
            "company": company,
            "source": source,
            "title": title,
            "sales_nav_url": sales_nav_url,
            "campaign": campaign,
            "list_id": list_id,
            "location": location,
            "bio": bio,
            "headline": headline,
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


def load_invite_sent_leads_with_names() -> dict[str, dict]:
    """
    Return invite_sent/pending leads with their names for inbox matching.
    {email: {linkedin_url, first_name, last_name}}
    """
    from config import MIN_DM_WAIT_DAYS
    init_db()
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT email, linkedin_url, first_name, last_name FROM leads
            WHERE linkedin_status IN ('invite_sent', 'pending')
            AND linkedin_url IS NOT NULL AND linkedin_url != ''
            AND (last_action_at IS NULL OR last_action_at <= datetime('now', :wait))
            ORDER BY last_action_at ASC
        """, {"wait": f"-{MIN_DM_WAIT_DAYS} days"}).fetchall()
    return {
        row["email"]: {
            "linkedin_url": row["linkedin_url"],
            "first_name": row["first_name"] or "",
            "last_name": row["last_name"] or "",
        }
        for row in rows
    }


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


def load_unscored_leads(campaign: str = None) -> list[dict]:
    """Return leads that have not been scored yet (score IS NULL)."""
    init_db()
    where = "WHERE score IS NULL AND linkedin_url IS NOT NULL AND linkedin_url != ''"
    params = []
    if campaign:
        where += " AND campaign = ?"
        params.append(campaign)
    with get_connection() as conn:
        rows = conn.execute(f"""
            SELECT email, first_name, last_name, title, company, headline, bio, campaign
            FROM leads
            {where}
            ORDER BY created_at DESC
        """, params).fetchall()
    return [dict(row) for row in rows]


def update_lead_score(email: str, score: int, reason: str, persona: str = None):
    """Store Claude's score, reasoning, and persona classification for a lead."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE leads SET score = ?, score_reason = ?, persona = ? WHERE email = ?",
            (score, reason, persona, email)
        )


def load_uncontacted_leads(campaign: str = None, min_score: int = None) -> list[dict]:
    """Return not_contacted leads that have a LinkedIn URL, ordered oldest first."""
    init_db()
    where = "WHERE linkedin_status = 'not_contacted' AND linkedin_url IS NOT NULL AND linkedin_url != ''"
    params = []
    if campaign:
        where += " AND campaign = ?"
        params.append(campaign)
    if min_score is not None:
        where += " AND score >= ?"
        params.append(min_score)
    with get_connection() as conn:
        rows = conn.execute(f"""
            SELECT email, first_name, last_name, linkedin_url, company, score, persona
            FROM leads
            {where}
            ORDER BY created_at DESC
        """, params).fetchall()
    return [dict(row) for row in rows]


def load_processed_emails() -> set[str]:
    """Return emails that have had a LinkedIn action taken (not just synced from CRM)."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT email FROM leads WHERE linkedin_status != 'not_contacted'
        """).fetchall()
    return {row["email"] for row in rows}


def count_processed_today() -> int:
    """Count connection requests (invite_sent) sent today, using local date."""
    init_db()
    today = datetime.now().date().isoformat()  # local date
    with get_connection() as conn:
        row = conn.execute("""
            SELECT COUNT(*) as n FROM activity_log
            WHERE result = 'invite_sent'
            AND DATE(timestamp, 'localtime') = ?
        """, (today,)).fetchone()
    return row["n"] if row else 0


def count_inmails_today() -> int:
    """Count InMails sent today, using local date."""
    init_db()
    today = datetime.now().date().isoformat()
    with get_connection() as conn:
        row = conn.execute("""
            SELECT COUNT(*) as n FROM activity_log
            WHERE result = 'inmail_sent'
            AND DATE(timestamp, 'localtime') = ?
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


def get_lead_fields(email: str) -> dict:
    """Return first_name and company for a lead, with safe fallbacks."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT first_name, company FROM leads WHERE email = ?", (email,)
        ).fetchone()
    if not row:
        return {"first_name": "there", "company": "your firm"}
    return {
        "first_name": row["first_name"] or "there",
        "company": row["company"] or "your firm",
    }


def get_or_create_list(sales_nav_url: str, name: str, campaign: str = None) -> dict:
    """Get existing list by URL or create a new one. Returns the list record as a dict."""
    init_db()
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id, name, campaign, last_scraped_at FROM lists WHERE sales_nav_url = ?",
            (sales_nav_url,)
        ).fetchone()
        if existing:
            return dict(existing)
        conn.execute(
            "INSERT INTO lists (name, sales_nav_url, campaign, created_at) VALUES (?, ?, ?, ?)",
            (name, sales_nav_url, campaign, now)
        )
        row = conn.execute(
            "SELECT id, name, campaign, last_scraped_at FROM lists WHERE sales_nav_url = ?",
            (sales_nav_url,)
        ).fetchone()
        return dict(row)


def update_list_scraped_at(list_id: int):
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute("UPDATE lists SET last_scraped_at = ? WHERE id = ?", (now, list_id))


def get_list_sales_nav_urls(list_id: int) -> set[str]:
    """Return the set of sales_nav_urls already stored for a given list."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT sales_nav_url FROM leads WHERE list_id = ? AND sales_nav_url IS NOT NULL",
            (list_id,)
        ).fetchall()
    return {row["sales_nav_url"] for row in rows}


def get_all_lists() -> list[dict]:
    """Return all lists with lead counts."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT l.id, l.name, l.campaign, l.sales_nav_url,
                   l.created_at, l.last_scraped_at,
                   COUNT(ld.email) as lead_count
            FROM lists l
            LEFT JOIN leads ld ON ld.list_id = l.id
            GROUP BY l.id
            ORDER BY l.created_at DESC
        """).fetchall()
    return [dict(row) for row in rows]


def _result_to_status(result: str) -> str | None:
    """Map an activity result string to a canonical linkedin_status."""
    if result == "invite_sent":
        return "invite_sent"
    if result == "accepted":
        return "accepted"
    if result == "dm_sent":
        return "dm_sent"
    if result in ("pending", "skipped (pending)"):
        return "pending"
    if result == "inmail_sent":
        return "inmail_sent"
    if result and result.startswith("ignored"):
        return "ignored"
    if result and result.startswith("skipped"):
        return "ignored"
    return None
