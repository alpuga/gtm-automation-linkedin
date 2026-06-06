"""
Scrape workflow: pull a Sales Navigator list into the DB.

For each lead not yet in the list:
  - Visit their Sales Nav profile to extract LinkedIn URL + public email
  - Upsert into leads table tagged with list_id and campaign
  - Log a 'scraped' activity entry

Re-running against the same list URL picks up only new additions.
"""

import os
import time
import random
from datetime import datetime

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

import config
from crm import db
from linkedin.browser import launch_browser
from linkedin.sales_nav import (
    scrape_people_list,
    scrape_list_name,
    extract_linkedin_url,
    extract_email,
    synthetic_email,
)
from linkedin.profile import scrape_profile_details


def run(
    list_url: str,
    campaign: str = None,
    name: str = None,
    dry_run: bool = False,
    limit: int = None,
):
    if dry_run:
        print("--- DRY RUN MODE ---\n")

    if not os.path.exists(config.SESSION_FILE):
        print(f"Error: session file '{config.SESSION_FILE}' not found. Run setup_session.py first.")
        return

    db.init_db()

    with sync_playwright() as p:
        browser, _context, page = launch_browser(p)

        # Navigate to list page to grab name before full scrape
        print(f"Loading list: {list_url}")
        try:
            page.goto(list_url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(random.randint(2000, 3000))
        except PlaywrightTimeoutError:
            print("Error: could not load list page (timeout).")
            browser.close()
            return

        if "linkedin.com/login" in page.url or "linkedin.com/authwall" in page.url:
            print("Session expired. Re-run setup_session.py.")
            browser.close()
            return

        # Resolve list name: scraped → --name flag → fallback
        detected_name = scrape_list_name(page)
        list_name = name or detected_name or f"{campaign or 'list'} — {datetime.now().strftime('%b %d %Y')}"

        # Get or create the list record
        is_new_list = db.get_connection().execute(
            "SELECT id FROM lists WHERE sales_nav_url = ?", (list_url,)
        ).fetchone() is None

        if is_new_list and not campaign:
            print("Error: --campaign is required when adding a new list.")
            browser.close()
            return

        list_record = db.get_or_create_list(list_url, list_name, campaign)
        list_id = list_record["id"]
        resolved_campaign = campaign or list_record["campaign"]

        if is_new_list:
            print(f"New list: \"{list_name}\" (campaign: {resolved_campaign})")
        else:
            print(f"Known list: \"{list_record['name']}\" (campaign: {resolved_campaign})")

        # Scrape leads — pass limit so we stop paginating early when testing
        print("Scraping leads...")
        leads = scrape_people_list(page, list_url, limit=limit)
        print(f"Found {len(leads)} lead(s) in list.")

        if not leads:
            browser.close()
            return

        # Determine which are new
        existing_urls = db.get_list_sales_nav_urls(list_id)
        new_leads = [l for l in leads if l["sales_nav_url"] not in existing_urls]
        print(f"{len(new_leads)} new lead(s) ({len(leads) - len(new_leads)} already in DB).")

        if not new_leads:
            print("Nothing to do.")
            db.update_list_scraped_at(list_id)
            browser.close()
            return

        if limit:
            new_leads = new_leads[:limit]
            print(f"Limiting to {limit} lead(s).")

        total = len(new_leads)
        saved = 0
        no_linkedin = 0

        for i, lead in enumerate(new_leads, 1):
            label = f"{lead['name']} @ {lead.get('company', '?')}"
            print(f"[{i}/{total}] {label} ... ", end="", flush=True)

            if dry_run:
                print("dry-run")
                continue

            # Visit Sales Nav profile to extract LinkedIn URL + email
            try:
                page.goto(lead["sales_nav_url"], wait_until="domcontentloaded", timeout=30_000)
                page.wait_for_timeout(random.randint(2000, 3500))
            except PlaywrightTimeoutError:
                print("error (profile load timeout)")
                continue

            if "linkedin.com/login" in page.url or "linkedin.com/authwall" in page.url:
                print("session expired")
                print("Session expired mid-run. Re-run setup_session.py.")
                browser.close()
                return

            linkedin_url = extract_linkedin_url(page)
            public_email = extract_email(page)

            # Location comes from the Sales Nav list row (most reliable source)
            # Bio requires visiting the LinkedIn profile
            location = lead.get("location", "")
            bio = ""
            headline = ""
            if linkedin_url:
                details = scrape_profile_details(page, linkedin_url)
                if details.get("bio") == "__session_expired__":
                    print("session expired")
                    print("Session expired mid-run. Re-run setup_session.py.")
                    browser.close()
                    return
                bio = details.get("bio", "")
                headline = details.get("headline", "")
                if not location:
                    location = details.get("location", "")
                # Use LinkedIn profile company as fallback if Sales Nav didn't have it
                if not lead.get("company"):
                    lead["company"] = details.get("company", "")

            # Use real email as key if available, otherwise synthetic
            email_key = public_email if public_email else synthetic_email(lead["sales_nav_url"])

            db.upsert_lead(
                email_key,
                first_name=lead["first_name"],
                last_name=lead["last_name"],
                linkedin_url=linkedin_url or None,
                company=lead.get("company") or None,
                source="sales_nav",
                title=lead.get("title") or None,
                sales_nav_url=lead["sales_nav_url"],
                campaign=resolved_campaign,
                list_id=list_id,
                location=location or None,
                bio=bio or None,
                headline=headline or None,
            )
            saved += 1
            if not linkedin_url:
                no_linkedin += 1

            markers = []
            if linkedin_url:
                markers.append("linkedin ✓")
            if public_email:
                markers.append("email ✓")
            if lead.get("company"):
                markers.append(f"company ✓")
            if location:
                markers.append(f"📍 {location}")
            if bio:
                markers.append("bio ✓")
            print("saved" + (f"  {'  '.join(markers)}" if markers else ""))

            if i < total:
                time.sleep(random.uniform(8, 15))

        if not dry_run:
            db.update_list_scraped_at(list_id)

        browser.close()

    print(f"\nDone. {saved} new lead(s) saved.")
    if no_linkedin:
        print(f"  {no_linkedin} lead(s) have no LinkedIn URL — they will be skipped by outreach.")
    print(f"  Run `python run.py outreach --from-db --campaign {resolved_campaign}` to send connection requests.")
