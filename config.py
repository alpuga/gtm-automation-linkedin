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
DB_FILE = os.getenv("DB_FILE", "data/leads.db")
ACTIVITY_LOG = "data/activity_log.csv"  # legacy CSV — used by migration script only

# --- AI ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# --- Scoring ---
SCORE_THRESHOLD = int(os.getenv("SCORE_THRESHOLD", "6"))  # leads below this are skipped by outreach

# ICP description per campaign — used by the scoring workflow to prompt Claude
CAMPAIGN_ICPS = {
    "capital_advisory": (
        "Senior professionals at firms whose primary workflow involves outbound calling to source deals, "
        "originate transactions, or place capital — they are the ones doing the calling, not the businesses "
        "receiving it. This includes investment banks, M&A advisory boutiques, private equity firms, "
        "search funds, placement agents, and family offices doing proprietary deal sourcing or LP outreach. "
        "Ideal titles include: Director/VP/MD of Deal Sourcing, Business Development, Origination, or "
        "Capital Markets; M&A Origination; Investment Banking; Placement Agent; Deal Originator; "
        "Managing Partner at advisory, PE, or capital formation firms. "
        "Score HIGH if the person works at an advisory, PE, placement, or origination firm in a "
        "sourcing/BD/origination/fundraising role. "
        "Score LOW if the person is an in-house CFO, finance executive, or operator at an operating company "
        "(they are targets for capital, not the teams doing outbound), or if they work in accounting, FP&A, or treasury."
    ),
}

# --- Limits ---
DAILY_LIMIT = 40
INMAIL_DAILY_LIMIT = 50     # conservative — Sales Navigator gives ~50 credits/month
POST_RECENCY_DAYS = 60      # only engage with posts newer than this
MIN_DM_WAIT_DAYS = 1        # minimum days to wait after invite before sending follow-up DM

# --- Sequence messages ---

# Step 1 — sent with connection request (outreach workflow)
CONNECT_NOTE = (
    "Hi {first_name}, sent you an email about being your go-to guy for anything merch. "
    "Wanted to connect here to put a face to the name."
)

# Persona-specific connection notes for capital_advisory campaign.
# Selected automatically based on Claude's persona classification.
CONNECT_NOTES = {
    # Economic buyer — ROI and risk framing
    "md_partner": (
        "Hi {first_name}, building AI-native compliance infrastructure for deal sourcing teams. "
        "Most platforms miss the TCPA exposure in this workflow, thought it worth "
        "connecting given your work at your firm."
    ),
    # Day-to-day power user — workflow and credibility
    "vp_origination": (
        "Hi {first_name}, building an AI calling platform for deal sourcing and "
        "origination teams. Most platforms skip the TCPA piece entirely, curious to "
        "connect with people running these workflows at your firm."
    ),
    # Gatekeeper — speak their language directly
    "gc_compliance": (
        "Hi {first_name}, building AI-native compliance infrastructure for deal sourcing teams. "
        "TCPA exposure in this workflow is real and most platforms don't address it, "
        "thought it relevant given your role at your firm."
    ),
    # Budget approver — efficiency framing
    "coo_cfo": (
        "Hi {first_name}, building AI-native compliance infrastructure for deal sourcing teams. "
        "Most platforms miss the TCPA exposure in this workflow, thought it worth "
        "connecting given your role at your firm."
    ),
    # PE/family office doing proprietary deal sourcing or LP outreach
    "pe_allocator": (
        "Hi {first_name}, building AI-native infrastructure for deal sourcing and "
        "LP outreach teams. Most platforms miss the TCPA exposure in this workflow, "
        "thought it worth connecting given your work at your firm."
    ),
    # Adjacent / referral — short, no pitch
    "other": (
        "Hi {first_name}, building AI-native infrastructure for deal sourcing teams. "
        "Relevant space to yours, thought it worth connecting."
    ),
}

# Step 2 — sent to already-connected leads (outreach workflow)
DM_TEXT = (
    "Hi {first_name}, I sent you an email about merch. Just wanted to follow up here to put a face to the email.\n\n"
    "I also understand you might not be the right person to talk to about this,"
    "if that's the case, would you mind pointing me in the right direction?\n\n"
    "Happy to put together some mockups for you guys."
)

# Sales Navigator InMail — sent to cold prospects via sales_nav_outreach workflow
INMAIL_SUBJECT = "Normally not a fan of InMails, but..."

INMAIL_BODY = (
    "Hi {first_name}, I thought sending you an inmail would be worth it.\n\n"
    "I help companies like yours create branded merch, from swag bags to event kits, "
    "without the usual headaches.\n\n"
    "Would love to put together some mockups for you guys if there's any interest. "
    "Happy to keep it quick! "
)

# Step 3 — sent when a connection request is accepted (check_status workflow)
FOLLOW_UP_DM = (
    "Hi {first_name}, appreciate the connect.\n\n"
    "Quick context on why I reached out, the FCC's February 2024 ruling classified "
    "AI-generated voices as 'artificial' under TCPA, applying full robocall obligations "
    "to AI outbound calls.\n\n"
    "Most dialers were built for consumer sales. They're missing what deal origination "
    "and fundraising teams specifically need: real-time DNC scrubbing, RND checks, "
    "non-bypassable disclosure, and per-call audit logs.\n\n"
    "I built a platform to solve this, compliance-first by design, not bolted on.\n\n"
    "If this is relevant to how your firm handles outbound origination or fundraising "
    "outreach, happy to have a 20-minute conversation. No deck, just a direct discussion."
)
