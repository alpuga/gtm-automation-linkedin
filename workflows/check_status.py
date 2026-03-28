"""
Check status workflow: visit each invite_sent lead's profile and check connection state.

For each invite_sent lead:
- pending      → log 'pending'
- connected    → accepted, send follow-up DM, log 'accepted'
- not_connected → invite ignored or expired, log 'ignored'
"""

import os
import time
import random

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

import config
from crm import leads as activity_log
from linkedin.browser import launch_browser
from linkedin.connect import is_pending
from linkedin.inbox import get_accepted_leads
from linkedin.message import send_follow_up_dm


def run(dry_run: bool = False, preview: bool = False, limit: int = None, profile_url: str = None, inbox: bool = False):
    if dry_run:
        print("--- DRY RUN MODE ---\n")

    if not os.getenv("INSTANTLY_API_KEY"):
        print("Error: set INSTANTLY_API_KEY in .env")
        return

    if not os.path.exists(config.SESSION_FILE):
        print(f"Error: session file '{config.SESSION_FILE}' not found. Run setup_session.py first.")
        return

    if profile_url:
        invite_sent_leads = {"test@test.com": profile_url}
    else:
        invite_sent_leads = activity_log.load_invite_sent_leads()
        if not invite_sent_leads:
            print("No invite_sent leads found in activity log.")
            return
        print(f"Found {len(invite_sent_leads)} invite_sent lead(s) to check.")

    with sync_playwright() as p:
        browser, _context, page = launch_browser(p)

        if inbox and not profile_url:
            print("Scanning inbox for accepted connections...")
            leads_with_names = activity_log.load_invite_sent_leads_with_names()
            matched = get_accepted_leads(page, leads_with_names)
            if "__session_expired__" in matched:
                print("Session expired. Re-run setup_session.py.")
                browser.close()
                return
            print(f"{len(matched)} lead(s) found in inbox (accepted).")
            if not matched:
                browser.close()
                print("\nDone.")
                return
            invite_sent_leads = matched

        if limit:
            invite_sent_leads = dict(list(invite_sent_leads.items())[:limit])
            print(f"Limiting to {limit} lead(s) for this run.")

        total = len(invite_sent_leads)

        for i, (email, linkedin_url) in enumerate(invite_sent_leads.items(), 1):
            print(f"[{i}/{total}] {email} ... ", end="", flush=True)

            if not linkedin_url:
                print("error (no linkedin_url in log)")
                continue

            if linkedin_url.startswith("http://"):
                linkedin_url = "https://" + linkedin_url[7:]

            try:
                page.goto(linkedin_url, wait_until="domcontentloaded", timeout=30_000)
                page.wait_for_timeout(random.randint(2000, 4000))
            except PlaywrightTimeoutError:
                print("error (page load timeout)")
                continue

            if os.getenv("DEBUG_HTML"):
                os.makedirs("data/screenshots", exist_ok=True)
                slug = email.replace("@", "_").replace(".", "_")
                with open(f"data/screenshots/{slug}_profile.html", "w") as f:
                    f.write(page.content())

            if "linkedin.com/login" in page.url or "linkedin.com/authwall" in page.url:
                print("session expired")
                print("Session expired mid-run. Re-run setup_session.py.")
                browser.close()
                return

            if "linkedin.com/login" in page.url or "linkedin.com/authwall" in page.url:
                print("session expired")
                print("Session expired mid-run. Re-run setup_session.py.")
                browser.close()
                return

            # Check pending first via More → Withdraw, then let send_follow_up_dm
            # handle accepted (1st degree) vs ignored (2nd/3rd) via degree check.
            if is_pending(page):
                print("pending")
                if not dry_run:
                    activity_log.log_activity(email, "pending", linkedin_url)
            else:
                first_name = activity_log.get_first_name(email)
                result = send_follow_up_dm(page, linkedin_url, first_name, dry_run, preview=preview)
                print(result)
                if result == "session_expired":
                    print("Session expired mid-run. Re-run setup_session.py.")
                    browser.close()
                    return
                if not dry_run:
                    activity_log.log_activity(email, result, linkedin_url)

            if i < total:
                time.sleep(random.uniform(30, 90))

        browser.close()

    print("\nDone.")
