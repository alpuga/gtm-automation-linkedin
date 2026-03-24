"""
Central configuration — message templates, limits, and file paths.
Edit this file to update sequence messages or adjust limits.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# --- Auth ---
SESSION_FILE = os.getenv("LINKEDIN_SESSION_FILE", "linkedin_session.json")

# --- Data ---
ACTIVITY_LOG = "data/activity_log.csv"
LEADS_FILE = "data/leads.csv"

# --- Limits ---
DAILY_LIMIT = 50
POST_RECENCY_DAYS = 60  # only engage with posts newer than this

# --- Sequence messages ---

# Step 1 — sent with connection request (outreach workflow)
CONNECT_NOTE = (
    "Hi {first_name}, sent you an email about taking care of all your merch needs. "
    "Wanted to connect here to put a face to the name."
)

# Step 2 — sent to already-connected leads (outreach workflow)
DM_TEXT = (
    "Hi {first_name}, I sent you an email about merch. Just wanted to follow up here "
    "to put a face to the email. Let me know what your merch needs are and I'd be happy "
    "to put together some mockups for you to check out. No pressure at all, just thought I'd offer."
)

# Step 3 — sent when a connection request is accepted (check_status workflow)
FOLLOW_UP_DM = (
    "Hi {first_name}, great connecting! I sent you an email about merch recently — "
    "just wanted to follow up here too. Happy to put together some mockups if you're "
    "ever curious. No pressure at all!"
)
