"""
Outreach workflow: fetch contacted leads from Instantly → act on LinkedIn.

For each lead with a LinkedIn URL:
- Not connected  → send connection request with note
- Connected      → send direct message
- Pending/other  → skip
"""

import os
import time
import random
import subprocess

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

import config
from crm.instantly import InstantlyClient, extract_linkedin_url
from crm import leads as activity_log
from linkedin.browser import launch_browser
from linkedin.connect import detect_connection_state, send_connection_request
from linkedin.message import send_dm
from linkedin.utils import find_profile_action


def handle_lead(page, lead: dict, dry_run: bool = False) -> str:
    linkedin_url = extract_linkedin_url(lead)
    if not linkedin_url:
        return "skipped (no linkedin url)"
    if linkedin_url.startswith("http://"):
        linkedin_url = "https://" + linkedin_url[7:]

    first_name = lead.get("first_name") or lead.get("firstName") or "there"

    try:
        page.goto(linkedin_url, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(random.randint(3000, 6000))
    except PlaywrightTimeoutError:
        return "error (page load timeout)"

    if "linkedin.com/404" in page.url or page.title() == "Profile Not Found | LinkedIn":
        return "skipped (profile not found)"

    if os.getenv("DEBUG_HTML"):
        os.makedirs("data/screenshots", exist_ok=True)
        email = lead.get("email", "unknown")
        with open(f"data/screenshots/{email.replace('@','_').replace('.','_')}_debug.html", "w") as f:
            f.write(page.content())

    state = detect_connection_state(page, linkedin_url)

    if state == "session_expired":
        return "session-expired"
    if state == "pending":
        return "skipped (pending)"
    if state == "out_of_network":
        return "skipped (sales navigator - out of network)"
    if state == "disabled":
        return "skipped (connection requests disabled)"
    if state == "error":
        return "error (page load timeout)"

    if state == "connected":
        if dry_run:
            return "dry-run: would message"
        try:
            page.goto(linkedin_url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(1500)
        except PlaywrightTimeoutError:
            return "error (page load timeout)"
        profile_card = page.locator("section[componentkey*='Topcard']")
        message_btn = find_profile_action(profile_card, "Message")
        if message_btn:
            return send_dm(page, message_btn, first_name, config.DM_TEXT)
        return "error (connected but message button not found)"

    # not_connected — send connection request
    if dry_run:
        return "dry-run: would connect"
    return send_connection_request(page, first_name)


def run(dry_run: bool = False, profile_url: str = None, reset_today: bool = False):
    if reset_today:
        activity_log.reset_today()
        return

    if profile_url and not dry_run:
        print("Error: --profile requires --dry-run.")
        return

    if dry_run:
        print("--- DRY RUN MODE ---\n")

    if not os.getenv("INSTANTLY_API_KEY"):
        print("Error: set INSTANTLY_API_KEY in .env")
        return

    if not os.path.exists(config.SESSION_FILE):
        print(f"Error: session file '{config.SESSION_FILE}' not found. Run setup_session.py first.")
        return

    if profile_url:
        leads = [{"email": "test@test.com", "first_name": "Test", "payload": {"linkedIn": profile_url}}]
        pending = leads
    else:
        client = InstantlyClient()
        print("Fetching leads from Instantly...")
        leads = client.fetch_leads()
        print(f"Fetched {len(leads)} contacted lead(s).")
        if not leads:
            print("No contacted leads found.")
            return

        processed = activity_log.load_processed_emails()
        pending = [l for l in leads if l.get("email") not in processed]
        print(f"{len(pending)} new lead(s) to process ({len(leads) - len(pending)} already done).")

        if not pending:
            print("Nothing to do.")
            return

        done_today = activity_log.count_processed_today()
        remaining = config.DAILY_LIMIT - done_today
        if remaining <= 0:
            print(f"Daily limit of {config.DAILY_LIMIT} reached. Run again tomorrow.")
            return
        pending = pending[:remaining]
        print(f"Daily limit: {config.DAILY_LIMIT} — {done_today} done today, processing up to {len(pending)} more.")

    connections_before = activity_log.count_connections_this_week()
    print(f"Connection requests sent this week (before this run): {connections_before}")

    with sync_playwright() as p:
        browser, _context, page = launch_browser(p)
        new_connections = 0

        for i, lead in enumerate(pending, 1):
            email = lead.get("email", "unknown")
            print(f"[{i}/{len(pending)}] {email} ... ", end="", flush=True)
            result = handle_lead(page, lead, dry_run=dry_run)
            print(result)

            if not dry_run:
                linkedin_url = extract_linkedin_url(lead) or ""
                activity_log.log_activity(email, result, linkedin_url)

            if result == "session-expired":
                subprocess.run([
                    "osascript", "-e",
                    'display notification "Re-run setup_session.py to log in again." with title "LinkedIn session expired"'
                ])
                print("\nLinkedIn session expired. Re-run setup_session.py then try again.")
                break

            if result == "invite_sent":
                new_connections += 1

            time.sleep(random.uniform(60, 180))

        browser.close()

    total_this_week = connections_before + new_connections
    print(f"\nDone. Connection requests this week: {total_this_week}")
    if total_this_week >= 100:
        print("WARNING: ~100 connection requests this week. LinkedIn may start blocking them.")
