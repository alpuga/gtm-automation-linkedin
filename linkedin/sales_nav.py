"""Scrape a Sales Navigator people list — returns lead dicts for each person."""

import os
import random
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


def scrape_people_list(page, list_url: str) -> list[dict]:
    """
    Paginate through a Sales Navigator people list and return a list of lead dicts.
    Each dict: {first_name, last_name, name, title, company, sales_nav_url, linkedin_url}
    """
    leads = []

    try:
        page.goto(list_url, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(random.randint(2000, 3000))
    except PlaywrightTimeoutError:
        print("error (page load timeout on list)")
        return leads

    if "linkedin.com/login" in page.url or "linkedin.com/authwall" in page.url:
        print("session_expired")
        return leads

    page_num = 1
    while True:
        if os.getenv("DEBUG_HTML"):
            os.makedirs("data/screenshots", exist_ok=True)
            with open(f"data/screenshots/sales_nav_list_p{page_num}.html", "w") as f:
                f.write(page.content())

        # Wait for lead cards
        try:
            page.wait_for_selector(
                "li[data-view-name='search-results-lead-result']", timeout=10_000
            )
        except PlaywrightTimeoutError:
            break

        cards = page.locator("li[data-view-name='search-results-lead-result']").all()
        for card in cards:
            lead = _extract_lead(card)
            if lead:
                leads.append(lead)

        # Next page
        next_btn = page.locator("button[aria-label='Next']")
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


def _extract_lead(card) -> dict | None:
    try:
        # Name link
        name_link = card.locator("a[data-view-name='search-results-lead-name']")
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
            title_el = card.locator("[data-view-name='search-results-lead-title']")
            if title_el.first.is_visible(timeout=500):
                title = title_el.first.inner_text().strip()
        except PlaywrightTimeoutError:
            pass

        # Company
        company = ""
        try:
            company_el = card.locator("[data-view-name='search-results-lead-company-name']")
            if company_el.first.is_visible(timeout=500):
                company = company_el.first.inner_text().strip()
        except PlaywrightTimeoutError:
            pass

        linkedin_url = _resolve_linkedin_url(card, sales_nav_url)

        parts = name.split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""

        return {
            "name": name,
            "first_name": first_name,
            "last_name": last_name,
            "title": title,
            "company": company,
            "sales_nav_url": sales_nav_url,
            "linkedin_url": linkedin_url,
        }
    except PlaywrightTimeoutError:
        return None


def _resolve_linkedin_url(card, sales_nav_url: str) -> str:
    """Try to get the regular linkedin.com/in/ URL from the card, or derive it from the Sales Nav URL."""
    # Some cards surface the regular profile link directly
    try:
        link = card.locator("a[href*='linkedin.com/in/']")
        href = link.first.get_attribute("href", timeout=500)
        if href:
            return href.split("?")[0]
    except Exception:
        pass

    # Sales Nav URL format: /sales/lead/ACwAAAxxxxxx,NAME:john-doe
    if "NAME:" in sales_nav_url:
        slug = sales_nav_url.split("NAME:")[-1].split(",")[0].split("?")[0].lower()
        if slug:
            return f"https://www.linkedin.com/in/{slug}/"

    return ""
