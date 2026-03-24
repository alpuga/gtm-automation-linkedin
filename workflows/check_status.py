"""
Check status workflow: cross-reference sent invites against LinkedIn's pending list.

For each invite_sent lead:
- Accepted (1st degree, not in pending list) → send follow-up DM, log 'accepted'
- Still pending (in pending list)            → log 'pending'  [post liking: Phase 2]
- Ignored (not 1st degree, not in pending)   → log 'ignored'
"""

import os
import time
import random

from playwright.sync_api import sync_playwright

import config
from crm.instantly import InstantlyClient, get_first_name
from crm import leads as activity_log
from linkedin.browser import launch_browser
from linkedin.message import send_follow_up_dm
from linkedin.scraper import scrape_pending_vanity_names, extract_vanity_from_url


def run(dry_run: bool = False):
    if dry_run:
        print("--- DRY RUN MODE ---\n")

    if not os.getenv("INSTANTLY_API_KEY"):
        print("Error: set INSTANTLY_API_KEY in .env")
        return

    if not os.path.exists(config.SESSION_FILE):
        print(f"Error: session file '{config.SESSION_FILE}' not found. Run setup_session.py first.")
        return

    invite_sent_leads = activity_log.load_invite_sent_leads()
    if not invite_sent_leads:
        print("No invite_sent leads found in activity log.")
        return
    print(f"Found {len(invite_sent_leads)} invite_sent lead(s) to check.")

    print("Fetching leads from Instantly for name lookup...")
    leads_by_email = InstantlyClient().fetch_leads_by_email()

    with sync_playwright() as p:
        browser, _context, page = launch_browser(p)

        print("Scraping pending invitations page...")
        try:
            pending_vanity_names = scrape_pending_vanity_names(page)
        except RuntimeError:
            print("LinkedIn session expired. Re-run setup_session.py then try again.")
            browser.close()
            return
        print(f"Found {len(pending_vanity_names)} pending invite(s) on LinkedIn.\n")

        potentially_accepted = []
        still_pending = []

        for email, linkedin_url in invite_sent_leads.items():
            vanity = extract_vanity_from_url(linkedin_url)
            if vanity and vanity in pending_vanity_names:
                still_pending.append((email, linkedin_url))
            else:
                potentially_accepted.append((email, linkedin_url))

        print(f"{len(potentially_accepted)} potentially accepted, {len(still_pending)} still pending.\n")

        # Potentially accepted — degree check inside send_follow_up_dm disambiguates
        # accepted (1st degree → DM) from ignored (2nd/3rd → log 'ignored')
        for i, (email, linkedin_url) in enumerate(potentially_accepted, 1):
            first_name = get_first_name(email, leads_by_email)
            print(f"[check {i}/{len(potentially_accepted)}] {email} ... ", end="", flush=True)

            if not linkedin_url:
                result = "error (no linkedin_url in log)"
            else:
                result = send_follow_up_dm(page, linkedin_url, first_name, dry_run)
            print(result)

            if result == "session_expired":
                print("Session expired mid-run. Re-run setup_session.py.")
                browser.close()
                return

            if not dry_run:
                activity_log.log_activity(email, result, linkedin_url)

            if i < len(potentially_accepted):
                time.sleep(random.uniform(30, 90))

        # Still pending — log only (post liking coming in Phase 2)
        for email, linkedin_url in still_pending:
            print(f"[pending] {email}")
            if not dry_run:
                activity_log.log_activity(email, "pending", linkedin_url)

        browser.close()

    print("\nDone.")
