"""
Scrape LinkedIn inbox to find leads who accepted a connection request.

LinkedIn's conversation list doesn't expose profile URLs — it uses internal
numeric IDs that don't match the vanity URLs stored in the DB. Instead we
match by full name (first_name + last_name) from the conversation list.
"""

import os
import random
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

MESSAGING_URL = "https://www.linkedin.com/messaging/"


def get_accepted_leads(page, leads_with_names: dict[str, dict]) -> dict[str, str]:
    """
    Scrape the LinkedIn inbox and return the subset of leads whose full name
    appears in a conversation thread.

    leads_with_names: {email: {linkedin_url, first_name, last_name}}
    Returns: {email: linkedin_url}
    """
    try:
        page.goto(MESSAGING_URL, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(random.randint(2000, 3000))
    except PlaywrightTimeoutError:
        print("error (inbox page load timeout)")
        return {}

    if "linkedin.com/login" in page.url or "linkedin.com/authwall" in page.url:
        return {"__session_expired__": ""}

    if os.getenv("DEBUG_HTML"):
        os.makedirs("data/screenshots", exist_ok=True)
        with open("data/screenshots/_inbox.html", "w") as f:
            f.write(page.content())

    # Build name → email lookup (lowercase full name for fuzzy-safe matching)
    name_lookup = {}
    for email, lead in leads_with_names.items():
        full_name = f"{lead['first_name']} {lead['last_name']}".strip().lower()
        if full_name:
            name_lookup[full_name] = email

    target_names = set(name_lookup.keys())  # lowercase full names we're hunting for
    inbox_names = _scrape_conversation_names(page, target_names)

    matched = {}
    for inbox_name in inbox_names:
        email = name_lookup.get(inbox_name.lower())
        if email:
            matched[email] = leads_with_names[email]["linkedin_url"]

    return matched


def _scrape_conversation_names(page, target_names: set[str]) -> set[str]:
    """
    Scroll through the inbox conversation list and collect sender names,
    stopping as soon as all target names have been found.

    Names are in: h3.msg-conversation-listitem__participant-names
    Scrollable container: ul.msg-conversations-container__conversations-list
    """
    names = set()
    found = set()

    for _ in range(30):  # max 30 scroll attempts (~750 conversations)
        prev_count = len(names)

        items = page.locator("h3.msg-conversation-listitem__participant-names").all()
        for item in items:
            try:
                text = item.inner_text(timeout=500).strip()
                if text:
                    names.add(text)
                    if text.lower() in target_names:
                        found.add(text.lower())
            except PlaywrightTimeoutError:
                continue

        # Stop early if we've found every lead we're looking for
        if found >= target_names:
            break

        if len(names) == prev_count:
            break  # No new conversations loaded — end of list

        # Scroll the conversation list container
        try:
            page.locator("ul.msg-conversations-container__conversations-list").evaluate(
                "el => el.scrollBy(0, el.clientHeight)"
            )
            page.wait_for_timeout(1200)
        except Exception:
            page.keyboard.press("End")
            page.wait_for_timeout(1200)

    return names
