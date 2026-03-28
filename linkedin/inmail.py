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
) -> str:
    """
    Navigate to a Sales Navigator profile page and send an InMail.
    Returns a result string suitable for activity logging.
    """
    try:
        page.goto(sales_nav_url, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(random.randint(2000, 3500))
    except PlaywrightTimeoutError:
        return "error (page load timeout)"

    if "linkedin.com/login" in page.url or "linkedin.com/authwall" in page.url:
        return "session_expired"

    if os.getenv("DEBUG_HTML"):
        os.makedirs("data/screenshots", exist_ok=True)
        slug = sales_nav_url.rstrip("/").split("/")[-1]
        with open(f"data/screenshots/{slug}_sales_nav_profile.html", "w") as f:
            f.write(page.content())

    # Find the Message / InMail button on the Sales Nav profile
    message_btn = None
    for selector in (
        "button[data-view-name='lead-cta-send-inmail']",
        "button[data-control-name='send_inmail']",
        "button[aria-label*='Message']",
        "button:has-text('Message')",
    ):
        el = page.locator(selector)
        try:
            if el.first.is_visible(timeout=2000):
                message_btn = el.first
                break
        except PlaywrightTimeoutError:
            continue

    if message_btn is None:
        return "error (message button not found)"

    if dry_run:
        return "dry-run: would send InMail"

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
        return "error (inmail body not found)"

    body_field.click()
    page.wait_for_timeout(300)
    page.keyboard.type(INMAIL_BODY.format(first_name=first_name), delay=20)
    page.wait_for_timeout(500)

    if preview:
        input("  → InMail ready. Press Enter here to continue (will NOT be sent)...")
        return "preview (not sent)"

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
        return "error (send button not found)"

    send_btn.click()
    page.wait_for_timeout(1500)
    return "inmail_sent"
