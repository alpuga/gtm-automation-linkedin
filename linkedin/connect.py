"""LinkedIn connection request automation."""

import os
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from config import CONNECT_NOTE
from linkedin.utils import find_profile_action


def is_pending(page) -> bool:
    """
    Return True if there is a pending outbound invite to the person on the current profile page.
    Checks for a direct 'Pending' button or a 'Withdraw' option in the More dropdown.
    """
    profile_card = page.locator("section[componentkey*='Topcard']")

    if find_profile_action(profile_card, "Pending"):
        return True

    more_btn = find_profile_action(profile_card, "More")
    if more_btn:
        try:
            more_btn.click()
            page.wait_for_timeout(800)
            withdraw = page.get_by_role("menuitem", name="Withdraw")
            try:
                if withdraw.first.is_visible(timeout=2000):
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(500)
                    return True
            except PlaywrightTimeoutError:
                pass
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
        except PlaywrightTimeoutError:
            pass

    return False


def detect_connection_state(page, linkedin_url: str) -> str:
    """
    Detect connection state using LinkedIn's custom-invite URL redirect behavior.

    Returns one of:
      'pending' | 'not_connected' | 'connected' | 'out_of_network' | 'disabled' |
      'session_expired' | 'error'
    """
    if is_pending(page):
        return "pending"

    vanity = page.url.rstrip("/").split("/")[-1]
    invite_url = f"https://www.linkedin.com/preload/custom-invite/?vanityName={vanity}"

    try:
        page.goto(invite_url, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(2000)
    except PlaywrightTimeoutError:
        return "error"

    if "linkedin.com/login" in page.url or "linkedin.com/authwall" in page.url:
        return "session_expired"
    if "linkedin.com/sales" in page.url:
        return "out_of_network"
    if "preload/custom-invite" in page.url:
        return "not_connected"
    if "/in/" in page.url:
        return "connected"
    return "disabled"


def send_connection_request(page, first_name: str, note: str = None) -> str:
    """Send a connection request with a note. Page must be on the custom-invite URL."""

    # Detect email-verification-required modal before interacting
    # LinkedIn shows this when the recipient has enabled "people you may know" protection
    try:
        if page.get_by_text("please enter their email", exact=False).first.is_visible(timeout=2000):
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
            return "skipped (email required)"
    except PlaywrightTimeoutError:
        pass

    # Click "Add a note"
    try:
        add_note_btn = page.get_by_role("button", name="Add a note")
        add_note_btn.first.wait_for(timeout=5000)
        add_note_btn.first.dispatch_event("click")
        page.wait_for_timeout(800)
    except PlaywrightTimeoutError:
        block = _check_for_blocking_modal(page)
        if block:
            return block
        os.makedirs("data/screenshots", exist_ok=True)
        page.screenshot(path="data/screenshots/_modal_add_note_not_found.png")
        return "error (add note button not found)"

    # Fill the note via JS to bypass overlapping dropdowns
    try:
        note_box = page.locator("textarea").first
        note_box.wait_for(state="attached", timeout=3000)
        note = (note or CONNECT_NOTE).format(first_name=first_name)[:300]
        page.evaluate(
            "([el, val]) => { el.value = val; el.dispatchEvent(new Event('input', {bubbles: true})); }",
            [note_box.element_handle(), note]
        )
        page.wait_for_timeout(500)
    except PlaywrightTimeoutError:
        return "error (note textarea not found)"

    # Send
    sent = False
    for label in ("Send", "Send invitation"):
        try:
            btn = page.get_by_role("button", name=label, exact=True)
            btn.first.wait_for(state="attached", timeout=2000)
            btn.first.dispatch_event("click")
            sent = True
            break
        except Exception:
            pass

    if not sent:
        os.makedirs("data/screenshots", exist_ok=True)
        page.screenshot(path="data/screenshots/_send_connection_modal_failed.png")
        return "error (send connection failed)"

    # Verify modal closed
    try:
        page.get_by_role("button", name="Add a note").first.wait_for(state="detached", timeout=5000)
    except PlaywrightTimeoutError:
        block = _check_for_blocking_modal(page)
        if block:
            return block
        os.makedirs("data/screenshots", exist_ok=True)
        page.screenshot(path="data/screenshots/_send_connection_verify_failed.png")
        return "error (modal did not close after send)"

    # Check for invitation limit notices — LinkedIn uses various phrasings
    for phrase in ("weekly limit", "invitation limit", "limit reached", "too many"):
        try:
            if page.get_by_text(phrase, exact=False).first.is_visible(timeout=1000):
                try:
                    page.get_by_role("button", name="Got it").first.click()
                except Exception:
                    pass
                return "limit_reached"
        except PlaywrightTimeoutError:
            continue

    block = _check_for_blocking_modal(page)
    if block:
        return block

    return "invite_sent"


def _check_for_blocking_modal(page) -> str | None:
    """Check for email-verification or other blocking modals. Returns skip reason or None."""
    # Try multiple selectors LinkedIn uses for the email verification step
    email_selectors = [
        lambda: page.get_by_role("textbox", name="Email address"),
        lambda: page.get_by_role("textbox", name="email"),
        lambda: page.locator("input[type='email']"),
        lambda: page.locator("input[name='email']"),
        lambda: page.locator("input[autocomplete='email']"),
    ]
    for selector_fn in email_selectors:
        try:
            el = selector_fn()
            if el.first.is_visible(timeout=1000):
                os.makedirs("data/screenshots", exist_ok=True)
                page.screenshot(path="data/screenshots/_email_required_modal.png")
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)
                return "skipped (email required)"
        except PlaywrightTimeoutError:
            continue

    # Catch any modal with email-related text as a fallback
    for phrase in ("Enter your email", "confirm your email", "verify your email", "add your email"):
        try:
            if page.get_by_text(phrase, exact=False).first.is_visible(timeout=500):
                os.makedirs("data/screenshots", exist_ok=True)
                page.screenshot(path="data/screenshots/_email_required_modal.png")
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)
                return "skipped (email required)"
        except PlaywrightTimeoutError:
            continue

    return None
