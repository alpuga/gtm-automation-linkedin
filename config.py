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
DATA_DIR = "data"
DB_FILE = "data/leads.db"
ACTIVITY_LOG = "data/activity_log.csv"  # legacy CSV — used by migration script only

# --- Limits ---
DAILY_LIMIT = 40
POST_RECENCY_DAYS = 60      # only engage with posts newer than this
MIN_DM_WAIT_DAYS = 1        # minimum days to wait after invite before sending follow-up DM

# --- Sequence messages ---

# Step 1 — sent with connection request (outreach workflow)
CONNECT_NOTE = (
    "Hi {first_name}, sent you an email about taking care of all your merch needs. "
    "Wanted to connect here to put a face to the name."
)

# Step 2 — sent to already-connected leads (outreach workflow)
DM_TEXT = (
    "Hi {first_name}, I sent you an email about merch. Just wanted to follow up here to put a face to the email.\n\n"
    "I also understand you might not be the right person to talk to about this,"
    "if that's the case, would you mind pointing me in the right direction?\n\n"
    "Happy to put together some mockups for you guys."
)

# Step 3 — sent when a connection request is accepted (check_status workflow)
FOLLOW_UP_DM = (
    "Hi {first_name}, great connecting!\n\n"
    "I emailed you recently about merch, wanted to make sure it didn't slip through the cracks.\n\n"
    "If someone else owns this, I'd love an intro. I can put together some mockups for you guys to check out."
)
