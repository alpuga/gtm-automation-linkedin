"""LinkedIn DM automation with connection degree check."""

import os
import random
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from config import FOLLOW_UP_DM
from linkedin.utils import find_profile_action


def get_connection_degree(profile_card) -> str | None:
    """
    Return '1st', '2nd', '3rd+' or None if not detectable.
    LinkedIn renders the degree badge as a <p> element with text like '· 1st'.
    """
    try:
        for degree in ("1st", "2nd", "3rd+"):
            badge = profile_card.locator("p").filter(has_text=degree)
            if badge.first.is_visible(timeout=2000):
                return degree
    except PlaywrightTimeoutError:
        pass
    return None


def send_dm(page, message_btn, first_name: str, template: str, preview: bool = False) -> str:
    """Click the Message button and send a DM using the given template.
    If preview=True, fills the compose box but does not send."""
    message_btn.click()
    page.wait_for_timeout(2500)

    # Try multiple selectors — LinkedIn's compose box placeholder text can vary
    compose = None
    for selector in (
        "div[role='textbox'][contenteditable='true']",
        "div.msg-form__contenteditable",
        "[data-artdeco-is-focused] div[role='textbox']",
    ):
        el = page.locator(selector)
        try:
            if el.first.is_visible(timeout=4000):
                compose = el.first
                break
        except PlaywrightTimeoutError:
            continue

    if compose is None:
        if os.getenv("DEBUG_HTML"):
            os.makedirs("data/screenshots", exist_ok=True)
            page.screenshot(path="data/screenshots/_compose_not_found.png")
        return "error (message compose not found)"

    try:
        msg = template.format(first_name=first_name)
        compose.click()
        page.wait_for_timeout(500)
        # Use keyboard.type for contenteditable divs — more reliable than fill()
        page.keyboard.type(msg, delay=20)
        page.wait_for_timeout(500)
        if preview:
            input("  → Message ready. Press Enter here to continue (message will NOT be sent)...")
            return "preview (not sent)"
        page.keyboard.press("Enter")
        return "messaged"
    except PlaywrightTimeoutError:
        return "error (message compose timeout)"


def send_follow_up_dm(page, linkedin_url: str, first_name: str, dry_run: bool, preview: bool = False) -> str:
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

    if os.getenv("DEBUG_HTML"):
        os.makedirs("data/screenshots", exist_ok=True)
        slug = linkedin_url.rstrip("/").split("/")[-1]
        with open(f"data/screenshots/{slug}_connected_profile.html", "w") as f:
            f.write(page.content())

    degree = get_connection_degree(profile_card)
    if degree != "1st":
        return f"ignored (not 1st degree — {degree or 'unknown'})"

    message_btn = find_profile_action(profile_card, "Message")
    if not message_btn:
        return "error (message button not found)"

    if dry_run:
        return "dry-run: would send follow-up DM"

    result = send_dm(page, message_btn, first_name, FOLLOW_UP_DM, preview=preview)
    # Remap generic "messaged" to "accepted" to distinguish from outreach DMs
    return "accepted" if result == "messaged" else result
