"""
Sales Navigator InMail workflow.

Scrapes a Sales Navigator people list → deduplicates against the DB →
sends InMails → logs activity.
"""

import os
import time
import random

from playwright.sync_api import sync_playwright

import config
from crm import db
from linkedin.browser import launch_browser
from linkedin.sales_nav import scrape_people_list
from linkedin.inmail import send_inmail


def _synthetic_email(sales_nav_url: str) -> str:
    """Derive a stable unique key from a Sales Navigator profile URL.
    URL format: /sales/lead/ACwAAAxxxxxx,NAME_SEARCH,key
    Use the profile ID (first segment before comma) as the key.
    """
    slug = sales_nav_url.rstrip("/").split("/sales/lead/")[-1].split(",")[0].lower()
    return f"sn_{slug}@salesnav.local"


def run(
    list_url: str = None,
    dry_run: bool = False,
    preview: bool = False,
    limit: int = None,
    profile_url: str = None,
):
    if dry_run:
        print("--- DRY RUN MODE ---\n")

    if not os.path.exists(config.SESSION_FILE):
        print(f"Error: session file '{config.SESSION_FILE}' not found. Run setup_session.py first.")
        return

    db.init_db()

    # Daily InMail limit check
    sent_today = db.count_inmails_today()
    if sent_today >= config.INMAIL_DAILY_LIMIT:
        print(f"Daily InMail limit of {config.INMAIL_DAILY_LIMIT} reached ({sent_today} sent today).")
        return
    remaining = config.INMAIL_DAILY_LIMIT - sent_today

    contacted = db.load_processed_emails()

    with sync_playwright() as p:
        browser, _context, page = launch_browser(p)

        if profile_url:
            leads = [{"name": "Test", "first_name": "Test", "last_name": "", "title": "", "company": "", "sales_nav_url": profile_url, "linkedin_url": ""}]
        else:
            print(f"Scraping list: {list_url}")
            leads = scrape_people_list(page, list_url)

        if not leads:
            print("No leads found in list.")
            browser.close()
            return

        print(f"Found {len(leads)} lead(s) in list.")

        new_leads = [
            lead for lead in leads
            if _synthetic_email(lead["sales_nav_url"]) not in contacted
        ]
        print(f"{len(new_leads)} new lead(s) after deduplication.")

        if limit:
            new_leads = new_leads[:limit]
            print(f"Limiting to {limit} lead(s) for this run.")

        new_leads = new_leads[:remaining]
        total = len(new_leads)

        if total == 0:
            print("Nothing to do.")
            browser.close()
            return

        for i, lead in enumerate(new_leads, 1):
            email_key = _synthetic_email(lead["sales_nav_url"])
            label = f"{lead['name']} @ {lead.get('company', '?')}"
            print(f"[{i}/{total}] {label} ... ", end="", flush=True)

            info = send_inmail(
                page,
                lead["sales_nav_url"],
                lead["first_name"],
                dry_run=dry_run,
                preview=preview,
            )
            result = info["result"]
            print(result)

            if result == "session_expired":
                print("Session expired mid-run. Re-run setup_session.py.")
                browser.close()
                return

            if not dry_run and result == "inmail_sent":
                # If a public email was found, use it as the primary key
                real_email = info["email"] or None
                key = real_email if real_email else email_key
                db.upsert_lead(
                    key,
                    first_name=lead["first_name"],
                    last_name=lead["last_name"],
                    linkedin_url=info["linkedin_url"] or None,
                    company=lead.get("company"),
                    source="sales_nav",
                    title=lead.get("title") or None,
                    sales_nav_url=lead["sales_nav_url"],
                )
                db.log_activity(key, "inmail_sent")

            if i < total:
                time.sleep(random.uniform(30, 60))

        browser.close()

    print("\nDone.")
