"""Send an InMail from a Sales Navigator profile page."""

import os
import random
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from config import INMAIL_SUBJECT, INMAIL_BODY


def send_inmail(
    page,
    sales_nav_url: str,
    first_name: str,
    dry_run: bool = False,
    preview: bool = False,
) -> dict:
    """
    Navigate to a Sales Navigator profile page and send an InMail.
    Returns a dict: {result, linkedin_url, email}
    - linkedin_url: /in/ URL if LinkedIn exposes it on the page, else ''
    - email: public email if listed in contact info section, else ''
    """
    def _ret(result):
        return {"result": result, "linkedin_url": "", "email": ""}

    try:
        page.goto(sales_nav_url, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(random.randint(2000, 3500))
    except PlaywrightTimeoutError:
        return _ret("error (page load timeout)")

    if "linkedin.com/login" in page.url or "linkedin.com/authwall" in page.url:
        return _ret("session_expired")

    # Extract contact info while we're on the profile page
    linkedin_url = _extract_linkedin_url(page)
    email = _extract_email(page)

    if os.getenv("DEBUG_HTML"):
        os.makedirs("data/screenshots", exist_ok=True)
        slug = sales_nav_url.rstrip("/").split("/")[-1]
        with open(f"data/screenshots/{slug}_sales_nav_profile.html", "w") as f:
            f.write(page.content())
        print(f"  [debug] linkedin_url={linkedin_url!r} email={email!r}")

    # Wait for the Message / InMail button to be ready
    message_btn = None
    for selector in (
        "button[data-anchor-send-inmail]",
        "button[aria-label*='Message']",
        "button:has-text('Message')",
    ):
        try:
            page.wait_for_selector(selector, state="visible", timeout=5000)
            message_btn = page.locator(selector).first
            break
        except PlaywrightTimeoutError:
            continue

    if message_btn is None:
        return {"result": "error (message button not found)", "linkedin_url": linkedin_url, "email": email}

    if dry_run:
        return {"result": "dry-run: would send InMail", "linkedin_url": linkedin_url, "email": email}

    message_btn.click()
    page.wait_for_timeout(2500)

    # Subject field
    subject_field = None
    for selector in (
        "input[name='subject']",
        "input[placeholder*='subject' i]",
        "input[aria-label*='subject' i]",
        "input[data-artdeco-is-focused]",
    ):
        el = page.locator(selector)
        try:
            if el.first.is_visible(timeout=3000):
                subject_field = el.first
                break
        except PlaywrightTimeoutError:
            continue

    if subject_field:
        subject_field.click()
        subject_field.fill(INMAIL_SUBJECT.format(first_name=first_name))
        page.wait_for_timeout(300)

    # Body field
    body_field = None
    for selector in (
        "div[role='textbox'][contenteditable='true']",
        "div.msg-form__contenteditable",
        "textarea[name='body']",
        "textarea[aria-label*='message' i]",
    ):
        el = page.locator(selector)
        try:
            if el.first.is_visible(timeout=3000):
                body_field = el.first
                break
        except PlaywrightTimeoutError:
            continue

    if body_field is None:
        return {"result": "error (inmail body not found)", "linkedin_url": linkedin_url, "email": email}

    body_field.focus()
    page.wait_for_timeout(300)
    page.keyboard.type(INMAIL_BODY.format(first_name=first_name), delay=20)
    page.wait_for_timeout(500)

    if preview:
        input("  → InMail ready. Press Enter here to continue (will NOT be sent)...")
        return {"result": "preview (not sent)", "linkedin_url": linkedin_url, "email": email}

    # Send button
    send_btn = None
    for selector in (
        "button[aria-label='Send']",
        "button[data-control-name='send']",
        "button:has-text('Send')",
    ):
        el = page.locator(selector)
        try:
            if el.first.is_visible(timeout=2000):
                send_btn = el.first
                break
        except PlaywrightTimeoutError:
            continue

    if send_btn is None:
        return {"result": "error (send button not found)", "linkedin_url": linkedin_url, "email": email}

    send_btn.click()
    page.wait_for_timeout(1500)
    return {"result": "inmail_sent", "linkedin_url": linkedin_url, "email": email}


def _extract_linkedin_url(page) -> str:
    """
    Open the Sales Nav profile More menu and grab the href from
    'View LinkedIn profile' — then close the menu without navigating.
    """
    more_btn = page.locator("button[data-x--lead-actions-bar-overflow-menu]")
    try:
        if not more_btn.first.is_visible(timeout=2000):
            return ""
        more_btn.first.click()
        page.wait_for_timeout(800)

        # Menu items are dynamically rendered after click
        view_link = page.locator("a:has-text('View LinkedIn profile')")
        if view_link.first.is_visible(timeout=2000):
            href = view_link.first.get_attribute("href") or ""
            page.keyboard.press("Escape")
            page.wait_for_timeout(400)
            if "/in/" in href:
                return href.split("?")[0]

        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
    except PlaywrightTimeoutError:
        pass
    return ""


def _extract_email(page) -> str:
    """
    Extract a public email from the Sales Navigator contact info section.
    Emails appear as mailto: links inside section[data-sn-view-name="lead-contact-info"]
    when the lead has made their email public.
    """
    el = page.locator(
        "section[data-sn-view-name='lead-contact-info'] a[href^='mailto:']"
    )
    try:
        if el.first.is_visible(timeout=1500):
            href = el.first.get_attribute("href") or ""
            return href.replace("mailto:", "").strip()
    except PlaywrightTimeoutError:
        pass
    return ""
