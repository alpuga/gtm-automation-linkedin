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
            "linkedin_url": "",  # not available in list view
        }
    except (PlaywrightTimeoutError, IndexError):
        return None
