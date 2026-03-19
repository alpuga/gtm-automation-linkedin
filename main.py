"""
Main automation script: fetch contacted leads from Instantly → act on LinkedIn.

For each lead with a LinkedIn URL:
- Not connected → send connection request with note
- Already connected → send direct message
- Pending / other → skip
"""

import os
import csv
import time
import random
import argparse
import subprocess
from datetime import datetime
import httpx
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

load_dotenv()

INSTANTLY_API_KEY = os.getenv("INSTANTLY_API_KEY")
SESSION_FILE = os.getenv("LINKEDIN_SESSION_FILE", "linkedin_session.json")
PROCESSED_LOG = "processed_leads.csv"
DAILY_LIMIT = 50

CONNECT_NOTE = "Hi {first_name}, shot you an email about merch. Wanted to connect here to put a face to the name"
DM_TEXT = "Hi {first_name}, I sent you an email about merch. Just wanted to follow up here to put a face to the email. Let me know what your merch needs are and I'd be happy to put together some mockups for you to check out. No pressure at all, just thought I'd offer."

INSTANTLY_LEADS_URL = "https://api.instantly.ai/api/v2/leads/list"


# ---------------------------------------------------------------------------
# Processed leads log
# ---------------------------------------------------------------------------

def load_processed_leads() -> set[str]:
    """Return set of emails already processed in previous runs."""
    if not os.path.exists(PROCESSED_LOG):
        return set()
    with open(PROCESSED_LOG, newline="") as f:
        return {row["email"] for row in csv.DictReader(f)}


def count_processed_today() -> int:
    """Count how many leads were processed today."""
    if not os.path.exists(PROCESSED_LOG):
        return 0
    today = datetime.now().date().isoformat()
    count = 0
    with open(PROCESSED_LOG, newline="") as f:
        for row in csv.DictReader(f):
            if row.get("timestamp", "").startswith(today):
                count += 1
    return count


def count_connections_this_week() -> int:
    """Count how many connection requests were sent in the last 7 days."""
    if not os.path.exists(PROCESSED_LOG):
        return 0
    cutoff = datetime.now().timestamp() - 7 * 24 * 3600
    count = 0
    with open(PROCESSED_LOG, newline="") as f:
        for row in csv.DictReader(f):
            if row.get("result") == "connected":
                try:
                    ts = datetime.fromisoformat(row["timestamp"]).timestamp()
                    if ts >= cutoff:
                        count += 1
                except (ValueError, KeyError):
                    pass
    return count


def log_processed_lead(email: str, result: str, linkedin_url: str = ""):
    """Append a lead to the processed log."""
    write_header = not os.path.exists(PROCESSED_LOG)
    with open(PROCESSED_LOG, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["email", "linkedin_url", "result", "timestamp"])
        if write_header:
            writer.writeheader()
        writer.writerow({"email": email, "linkedin_url": linkedin_url, "result": result, "timestamp": datetime.now().isoformat()})


# ---------------------------------------------------------------------------
# Instantly API
# ---------------------------------------------------------------------------

def fetch_contacted_leads() -> list[dict]:
    """Fetch all leads that have been sent at least one email from Instantly."""
    headers = {"Authorization": f"Bearer {INSTANTLY_API_KEY}"}
    leads = []
    starting_after = None

    while True:
        payload = {"limit": 100}
        if starting_after:
            payload["starting_after"] = starting_after

        resp = httpx.post(INSTANTLY_LEADS_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        batch = data.get("items", [])
        for lead in batch:
            if lead.get("timestamp_last_contact"):
                leads.append(lead)

        next_cursor = data.get("next_starting_after")
        if not next_cursor:
            break
        starting_after = next_cursor

    leads.sort(key=lambda l: l.get("timestamp_last_contact", ""), reverse=True)
    print(f"Fetched {len(leads)} contacted lead(s) from Instantly.")
    return leads


def extract_linkedin_url(lead: dict) -> str | None:
    """Try common field names for LinkedIn URL."""
    for field in ("linkedin_url", "linkedinUrl", "linkedin", "LinkedIn URL"):
        val = lead.get(field) or lead.get("variables", {}).get(field)
        if val and "linkedin.com" in val:
            return val.strip()
    # Instantly stores LinkedIn URL under payload.linkedIn
    val = lead.get("payload", {}).get("linkedIn")
    if val and "linkedin.com" in val:
        return val.strip()
    return None


# ---------------------------------------------------------------------------
# LinkedIn automation
# ---------------------------------------------------------------------------

def handle_lead(page, lead: dict, dry_run: bool = False) -> str:
    """Navigate to lead's LinkedIn profile and send connection or message."""
    linkedin_url = extract_linkedin_url(lead)
    if not linkedin_url:
        return "skipped (no linkedin url)"

    email = lead.get("email", "unknown")
    first_name = lead.get("first_name") or lead.get("firstName") or "there"

    try:
        page.goto(linkedin_url, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(random.randint(3000, 6000))  # simulate reading the profile
    except PlaywrightTimeoutError:
        return "error (page load timeout)"

    if "linkedin.com/404" in page.url or page.title() == "Profile Not Found | LinkedIn":
        return "skipped (profile not found)"

    # DEBUG: dump page structure to inspect button locations
    if os.getenv("DEBUG_HTML"):
        os.makedirs("screenshots", exist_ok=True)
        with open(f"screenshots/{email.replace('@','_').replace('.','_')}_debug.html", "w") as f:
            f.write(page.content())

    # Scope lookups to the profile top card section
    # to avoid sidebar "More profiles for you" buttons
    profile_card = page.locator("section[componentkey*='Topcard']")

    def find_action(name: str):
        """Find a profile action element — LinkedIn uses both <a> and <button>."""
        for role in ("link", "button"):
            el = profile_card.get_by_role(role, name=name)
            try:
                if el.first.is_visible(timeout=2000):
                    return el.first
            except PlaywrightTimeoutError:
                pass
        return None

    # --- Debug: print all visible links and buttons in profile card ---
    if os.getenv("DEBUG_HTML"):
        for role in ("link", "button"):
            els = profile_card.get_by_role(role).all()
            for el in els:
                try:
                    if el.is_visible():
                        print(f"  [{role}] text='{el.inner_text().strip()[:50]}' aria-label='{el.get_attribute('aria-label')}'")
                except Exception:
                    pass

    # --- Detect connection state ---
    if find_action("Pending"):
        return "skipped (pending)"

    # Check direct Connect button first
    connect_el = find_action("Connect")
    if connect_el:
        if dry_run:
            return "dry-run: would connect"
        return _send_connection(page, connect_el, first_name)

    # Check More menu for Connect BEFORE falling back to Message
    # (LinkedIn shows Message/InMail for non-connected profiles too)
    more_el = find_action("More")
    if more_el:
        try:
            more_el.click()
            page.wait_for_timeout(800)

            if os.getenv("DEBUG_HTML"):
                items = page.get_by_role("menuitem").all()
                for item in items:
                    try:
                        print(f"  [menuitem] text='{item.inner_text().strip()[:50]}' aria-label='{item.get_attribute('aria-label')}'")
                    except Exception:
                        pass

            connect_in_menu = page.get_by_role("menuitem", name="connect")
            if connect_in_menu.first.is_visible(timeout=2000):
                if dry_run:
                    return "dry-run: would connect (via more menu)"
                connect_in_menu.first.click(no_wait_after=True)
                page.wait_for_timeout(1500)
                return _send_connection_modal(page, first_name)

            # No Connect in More menu — close it and fall through to Message
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
        except PlaywrightTimeoutError:
            pass

    # Only use Message if there's no Connect option anywhere (truly 1st-degree connected)
    message_el = find_action("Message")
    if message_el:
        if dry_run:
            return "dry-run: would message"
        return _send_message(page, message_el, first_name)

    # Check if we've been redirected to the login page (session expired)
    if "linkedin.com/login" in page.url or "linkedin.com/authwall" in page.url:
        return "session-expired"

    # Save a screenshot so we can inspect what LinkedIn is actually showing
    os.makedirs("screenshots", exist_ok=True)
    screenshot_path = f"screenshots/{email.replace('@', '_').replace('.', '_')}.png"
    page.screenshot(path=screenshot_path)
    print(f"  → screenshot saved: {screenshot_path}")

    return "skipped (unknown state)"



def _check_for_blocking_modal(page) -> str | None:
    """
    Detect known modals that block the connection flow.
    Returns a skip reason string if one is found and dismissed, else None.
    """
    # "Enter email" modal
    email_input = page.get_by_role("textbox", name="Email address")
    try:
        if email_input.first.is_visible(timeout=2000):
            dismiss = page.get_by_role("button", name="Cancel") or page.get_by_role("button", name="Close")
            try:
                dismiss.first.click()
            except Exception:
                pass
            return "skipped (email required)"
    except PlaywrightTimeoutError:
        pass

    # Generic "Got it" / rate-limit notice
    for label in ("Got it", "Dismiss", "Close"):
        try:
            btn = page.get_by_role("button", name=label)
            if btn.first.is_visible(timeout=1000):
                btn.first.click()
                return f"skipped (linkedin notice: {label.lower()})"
        except PlaywrightTimeoutError:
            pass

    return None


def _send_connection_modal(page, first_name: str) -> str:
    """Handle the connection modal after it's already been triggered (e.g. via More menu)."""

    # Click "Add a note" — use force=True to bypass any overlapping dropdown
    try:
        add_note_btn = page.get_by_role("button", name="Add a note")
        add_note_btn.first.wait_for(timeout=5000)
        add_note_btn.first.dispatch_event("click")
        page.wait_for_timeout(800)
    except PlaywrightTimeoutError:
        os.makedirs("screenshots", exist_ok=True)
        page.screenshot(path="screenshots/_modal_add_note_not_found.png")
        return "error (add note button not found)"

    # Fill the note via JavaScript to bypass the overlapping More menu dropdown
    try:
        note_box = page.locator("textarea").first
        note_box.wait_for(state="attached", timeout=3000)
        note = CONNECT_NOTE.format(first_name=first_name)[:300]
        page.evaluate(
            "([el, val]) => { el.value = val; el.dispatchEvent(new Event('input', {bubbles: true})); }",
            [note_box.element_handle(), note]
        )
        page.wait_for_timeout(500)
    except PlaywrightTimeoutError:
        return "error (note textarea not found)"

    # Send — use dispatch_event to bypass overlapping dropdown
    for label in ("Send", "Send invitation"):
        try:
            btn = page.get_by_role("button", name=label, exact=True)
            btn.first.wait_for(state="attached", timeout=2000)
            btn.first.dispatch_event("click")
            return "connected"
        except Exception:
            pass

    os.makedirs("screenshots", exist_ok=True)
    page.screenshot(path="screenshots/_send_connection_modal_failed.png")
    return "error (send connection failed)"


def _send_connection(page, connect_btn, first_name: str) -> str:
    # Extract vanity name from the current profile URL and navigate to the custom invite page
    vanity = page.url.rstrip("/").split("/")[-1]
    invite_url = f"https://www.linkedin.com/preload/custom-invite/?vanityName={vanity}"
    page.goto(invite_url, wait_until="domcontentloaded", timeout=30_000)
    page.wait_for_timeout(2000)
    return _send_connection_modal(page, first_name)

    os.makedirs("screenshots", exist_ok=True)
    page.screenshot(path="screenshots/_send_connection_failed.png")
    return "error (send connection failed)"


def _send_message(page, message_btn, first_name: str) -> str:
    message_btn.click()
    page.wait_for_timeout(1500)

    # Find the compose box
    compose = page.get_by_role("textbox", name="Write a message…")
    try:
        compose.first.wait_for(timeout=5000)
        msg = DM_TEXT.format(first_name=first_name)
        compose.first.fill(msg)
        page.wait_for_timeout(500)
        compose.first.press("Enter")
        return "messaged"
    except PlaywrightTimeoutError:
        return "error (message compose timeout)"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Visit profiles and detect state but do not send anything.")
    parser.add_argument("--profile", type=str, help="Test against a single LinkedIn profile URL.")
    parser.add_argument("--reset-today", action="store_true", help="Remove today's entries from the processed log to reset the daily limit.")
    args = parser.parse_args()
    dry_run = args.dry_run

    if args.reset_today:
        if not os.path.exists(PROCESSED_LOG):
            print("No processed_leads.csv found — nothing to reset.")
            return
        today = datetime.now().date().isoformat()
        with open(PROCESSED_LOG, newline="") as f:
            rows = list(csv.DictReader(f))
        kept = [r for r in rows if not r.get("timestamp", "").startswith(today)]
        removed = len(rows) - len(kept)
        with open(PROCESSED_LOG, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["email", "result", "timestamp"])
            writer.writeheader()
            writer.writerows(kept)
        print(f"Removed {removed} entry/entries from today. Daily limit reset.")
        return

    if args.profile and not dry_run:
        print("Error: --profile requires --dry-run to prevent accidental sends during testing.")
        return

    if dry_run:
        print("--- DRY RUN MODE — no messages or connection requests will be sent ---\n")

    if not INSTANTLY_API_KEY or INSTANTLY_API_KEY == "your_key_here":
        print("Error: set INSTANTLY_API_KEY in .env")
        return

    if not os.path.exists(SESSION_FILE):
        print(f"Error: LinkedIn session file '{SESSION_FILE}' not found.")
        print("Run setup_session.py first.")
        return

    if args.profile:
        # Single profile test mode — skip all lead filtering and limits
        leads = [{"email": "test@test.com", "first_name": "Test", "payload": {"linkedIn": args.profile}}]
        pending = leads
    else:
        leads = fetch_contacted_leads()
        if not leads:
            print("No contacted leads found.")
            return

        processed = load_processed_leads()
        pending = [l for l in leads if l.get("email") not in processed]
        print(f"{len(pending)} new lead(s) to process ({len(leads) - len(pending)} already done.")

        if not pending:
            print("Nothing to do.")
            return

        done_today = count_processed_today()
        remaining_today = DAILY_LIMIT - done_today
        if remaining_today <= 0:
            print(f"Daily limit of {DAILY_LIMIT} reached. Run again tomorrow.")
            return
        pending = pending[:remaining_today]
        print(f"Daily limit: {DAILY_LIMIT} — {done_today} done today, processing up to {len(pending)} more.")

    connections_before = count_connections_this_week()
    print(f"Connection requests sent this week (before this run): {connections_before}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-infobars",
                "--window-size=1366,768",
            ]
        )
        context = browser.new_context(
            storage_state=SESSION_FILE,
            viewport={"width": 1366, "height": 768},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="America/New_York",
        )
        # Remove the navigator.webdriver flag that headless Chrome exposes
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = context.new_page()

        new_connections = 0
        for i, lead in enumerate(pending, 1):
            email = lead.get("email", "unknown")
            print(f"[{i}/{len(pending)}] {email} ... ", end="", flush=True)
            result = handle_lead(page, lead, dry_run=dry_run)
            print(result)
            if not dry_run:
                linkedin_url = extract_linkedin_url(lead) or ""
                log_processed_lead(email, result, linkedin_url)
            if result == "session-expired":
                subprocess.run([
                    "osascript", "-e",
                    'display notification "Re-run setup_session.py to log in again." with title "LinkedIn session expired"'
                ])
                print("\nLinkedIn session expired. Re-run setup_session.py then try again.")
                break
            if result == "skipped (unknown state)":
                subprocess.run([
                    "osascript", "-e",
                    f'display notification "Check terminal to continue." with title "Unknown state: {email}"'
                ])
                input("  → Press Enter to continue to the next lead...")
            if result == "connected":
                new_connections += 1
            time.sleep(random.uniform(60, 180))

        browser.close()

    total_this_week = connections_before + new_connections
    print(f"\nDone. Connection requests this week: {total_this_week}")
    if total_this_week >= 100:
        print("WARNING: You've hit ~100 connection requests this week. LinkedIn may start blocking them.")


if __name__ == "__main__":
    main()
