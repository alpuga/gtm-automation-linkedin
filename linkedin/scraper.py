"""Scrape LinkedIn's sent invitations page for still-pending vanity names."""

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

INVITATION_MANAGER_URL = "https://www.linkedin.com/mynetwork/invitation-manager/sent/"


def extract_vanity_from_url(linkedin_url: str) -> str | None:
    """Extract normalized vanity name from a LinkedIn profile URL."""
    if not linkedin_url or "/in/" not in linkedin_url:
        return None
    vanity = linkedin_url.split("/in/")[-1].split("?")[0].rstrip("/").lower()
    return vanity or None


def scrape_pending_vanity_names(page) -> set[str]:
    """
    Scrape the sent invitations page and return the set of vanity names
    whose invitations are still pending.

    Raises RuntimeError("session-expired") if the session is invalid.
    """
    page.goto(INVITATION_MANAGER_URL, wait_until="domcontentloaded", timeout=30_000)
    page.wait_for_timeout(3000)

    if "linkedin.com/login" in page.url or "linkedin.com/authwall" in page.url:
        raise RuntimeError("session-expired")

    # Scroll to load all invitations (infinite scroll)
    prev_count = 0
    for _ in range(50):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(2000)
        current_count = len(page.locator("a[href*='/in/']").all())
        if current_count == prev_count:
            break
        prev_count = current_count

    pending = set()
    for link in page.locator("a[href*='/in/']").all():
        href = link.get_attribute("href") or ""
        vanity = extract_vanity_from_url(href)
        if vanity:
            pending.add(vanity)

    return pending
