"""LinkedIn DM automation with connection degree check."""

import random
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from config import FOLLOW_UP_DM
from linkedin.utils import find_profile_action


def get_connection_degree(profile_card) -> str | None:
    """
    Return '1st', '2nd', '3rd+' or None if not detectable.
    LinkedIn shows a degree badge near the profile name.
    """
    try:
        for degree in ("1st", "2nd", "3rd+"):
            badge = profile_card.locator("span[aria-hidden='true']").filter(has_text=degree)
            if badge.first.is_visible(timeout=2000):
                return degree
    except PlaywrightTimeoutError:
        pass
    return None


def send_dm(page, message_btn, first_name: str, template: str) -> str:
    """Click the Message button and send a DM using the given template."""
    message_btn.click()
    page.wait_for_timeout(1500)

    compose = page.get_by_role("textbox", name="Write a message…")
    try:
        compose.first.wait_for(timeout=5000)
        msg = template.format(first_name=first_name)
        compose.first.fill(msg)
        page.wait_for_timeout(500)
        compose.first.press("Enter")
        return "messaged"
    except PlaywrightTimeoutError:
        return "error (message compose timeout)"


def send_follow_up_dm(page, linkedin_url: str, first_name: str, dry_run: bool) -> str:
    """
    Visit an accepted connection's profile and send a follow-up DM.
    Checks connection degree first — only sends if 1st degree (DM, not InMail).
    """
    if linkedin_url.startswith("http://"):
        linkedin_url = "https://" + linkedin_url[7:]

    try:
        page.goto(linkedin_url, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(random.randint(2000, 4000))
    except PlaywrightTimeoutError:
        return "error (page load timeout)"

    if "linkedin.com/login" in page.url or "linkedin.com/authwall" in page.url:
        return "session_expired"

    if "linkedin.com/404" in page.url or page.title() == "Profile Not Found | LinkedIn":
        return "error (profile not found)"

    profile_card = page.locator("section[componentkey*='Topcard']")

    degree = get_connection_degree(profile_card)
    if degree != "1st":
        return f"ignored (not 1st degree — {degree or 'unknown'})"

    message_btn = find_profile_action(profile_card, "Message")
    if not message_btn:
        return "error (message button not found)"

    if dry_run:
        return "dry-run: would send follow-up DM"

    result = send_dm(page, message_btn, first_name, FOLLOW_UP_DM)
    # Remap generic "messaged" to "accepted" to distinguish from outreach DMs
    return "accepted" if result == "messaged" else result
