"""Sales Navigator scraping — list pagination, profile data extraction."""

import os
import random
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


def scrape_people_list(page, list_url: str, limit: int = None) -> list[dict]:
    """
    Paginate through a Sales Navigator people list and return a list of lead dicts.
    Each dict: {first_name, last_name, name, title, company, sales_nav_url, linkedin_url}
    Stops paginating early if limit is reached.
    """
    leads = []

    try:
        page.goto(list_url, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(random.randint(3000, 4000))
    except PlaywrightTimeoutError:
        print("error (page load timeout on list)")
        return leads

    if "linkedin.com/login" in page.url or "linkedin.com/authwall" in page.url:
        print("session_expired")
        return leads

    page_num = 1
    while True:
        # Wait for rows to be populated
        try:
            page.wait_for_selector("tr[data-x--people-list--row]", timeout=15_000)
        except PlaywrightTimeoutError:
            print(f"  (no rows found on page {page_num})")
            break

        page.wait_for_timeout(800)

        if os.getenv("DEBUG_HTML"):
            os.makedirs("data/screenshots", exist_ok=True)
            with open(f"data/screenshots/sales_nav_list_p{page_num}.html", "w") as f:
                f.write(page.content())

        rows = page.locator("tr[data-x--people-list--row]").all()
        for row in rows:
            lead = _extract_lead(row)
            if lead:
                leads.append(lead)
                if limit and len(leads) >= limit:
                    return leads

        # Next page button
        next_btn = page.locator("button[class*='_next-btn']")
        try:
            if next_btn.first.is_visible(timeout=2000) and next_btn.first.is_enabled():
                next_btn.first.click()
                page.wait_for_timeout(random.randint(2000, 3000))
                page_num += 1
            else:
                break
        except PlaywrightTimeoutError:
            break

    return leads


def _extract_lead(row) -> dict | None:
    try:
        # Name and Sales Nav URL
        name_link = row.locator("a.lists-detail__view-profile-name-link")
        if not name_link.first.is_visible(timeout=1000):
            return None

        name = name_link.first.inner_text().strip()
        href = name_link.first.get_attribute("href") or ""
        if href.startswith("/"):
            sales_nav_url = "https://www.linkedin.com" + href
        else:
            sales_nav_url = href

        # Title
        title = ""
        try:
            title_el = row.locator("div[data-anonymize='job-title']")
            if title_el.first.is_visible(timeout=500):
                title = title_el.first.inner_text().strip()
        except PlaywrightTimeoutError:
            pass

        # Company
        company = ""
        try:
            company_el = row.locator("span[data-anonymize='company-name']")
            if company_el.first.is_visible(timeout=500):
                company = company_el.first.inner_text().strip()
        except PlaywrightTimeoutError:
            pass

        # Location — available directly in the list row
        location = ""
        try:
            loc_el = row.locator("td[data-anonymize='location']")
            if loc_el.first.is_visible(timeout=500):
                location = loc_el.first.inner_text().strip()
        except PlaywrightTimeoutError:
            pass

        parts = name.split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""

        return {
            "name": name,
            "first_name": first_name,
            "last_name": last_name,
            "title": title,
            "company": company,
            "location": location,
            "sales_nav_url": sales_nav_url,
            "linkedin_url": "",  # not available in list view
        }
    except (PlaywrightTimeoutError, IndexError):
        return None


def scrape_list_name(page) -> str:
    """Try to extract the list name from the Sales Navigator list page header."""
    for selector in (
        "h1[data-x--people-list--name]",
        "h1.list-header__name",
        "h1",
    ):
        try:
            el = page.locator(selector).first
            if el.is_visible(timeout=2000):
                text = el.inner_text().strip()
                if text and len(text) < 120:
                    return text
        except PlaywrightTimeoutError:
            continue
    # Fall back to page title (usually "List Name | Sales Navigator")
    title = page.title()
    if title and "|" in title:
        return title.split("|")[0].strip()
    return ""


def extract_linkedin_url(page) -> str:
    """Extract LinkedIn profile URL from a Sales Navigator profile page via the More menu."""
    more_btn = page.locator("button[data-x--lead-actions-bar-overflow-menu]")
    try:
        if not more_btn.first.is_visible(timeout=2000):
            return ""
        more_btn.first.click()
        page.wait_for_timeout(800)

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


def extract_email(page) -> str:
    """Extract public email from a Sales Navigator profile page contact info section."""
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


def synthetic_email(sales_nav_url: str) -> str:
    """Derive a stable unique key from a Sales Navigator profile URL."""
    slug = sales_nav_url.rstrip("/").split("/sales/lead/")[-1].split(",")[0].lower()
    return f"sn_{slug}@salesnav.local"
