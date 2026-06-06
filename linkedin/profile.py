"""Scrape data points from a LinkedIn profile page."""

import os
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


def scrape_profile_details(page, linkedin_url: str) -> dict:
    """
    Navigate to a LinkedIn profile and extract bio, location, and company.
    Returns {"bio": str, "location": str, "company": str}.
    Caller is responsible for checking session state after this call.
    """
    try:
        page.goto(linkedin_url, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(2500)
    except PlaywrightTimeoutError:
        return {"bio": "", "location": "", "company": ""}

    if "linkedin.com/login" in page.url or "linkedin.com/authwall" in page.url:
        return {"bio": "__session_expired__", "location": "", "company": ""}

    if os.getenv("DEBUG_HTML"):
        os.makedirs("data/screenshots", exist_ok=True)
        slug = linkedin_url.rstrip("/").split("/in/")[-1].split("/")[0]
        with open(f"data/screenshots/{slug}_profile.html", "w") as f:
            f.write(page.content())

    return {
        "location": _scrape_location(page),
        "bio": _scrape_bio(page),
        "company": _scrape_company(page),
        "headline": _scrape_headline(page),
    }


def _scrape_location(page) -> str:
    selectors = [
        "span.text-body-small.inline.t-black--light.break-words",
        "section[data-section='intro'] span.text-body-small",
        "li.pv-text-details__left-panel.mt2 span",
        "div.pv-text-details__left-panel span.text-body-small",
    ]
    for selector in selectors:
        try:
            el = page.locator(selector).first
            if el.is_visible(timeout=1500):
                text = el.inner_text().strip()
                if text and len(text) < 80:
                    return text
        except PlaywrightTimeoutError:
            continue
    return ""


def _scrape_company(page) -> str:
    # LinkedIn top card shows "Current Company · Education" summary.
    # Find the first paragraph containing " · " and take the part before it.
    try:
        for el in page.locator("main p:has-text(' · ')").all():
            text = el.inner_text().strip()
            if " · " in text and len(text) < 120:
                company = text.split(" · ")[0].strip()
                if company and len(company) < 80:
                    return company
    except PlaywrightTimeoutError:
        pass
    return ""


def _scrape_headline(page) -> str:
    # The top card sits OUTSIDE <main>. It's wrapped in an <a href="/in/..."> link.
    # Inside that anchor: <p>Name</p><div><p>Headline</p></div> are siblings.
    # Targeting the /in/ href avoids matching unrelated anchors deeper in the page.
    try:
        for el in page.locator("a[href*='/in/'] p + div > p").all():
            try:
                text = el.inner_text().strip()
                if 10 < len(text) < 220:
                    return text
            except Exception:
                continue
    except PlaywrightTimeoutError:
        pass
    return ""


def _scrape_bio(page) -> str:
    # Find the About section by its h2 heading, then get the first substantial span
    try:
        about_section = page.locator("section:has(h2:has-text('About'))")
        if about_section.first.is_visible(timeout=3000):
            for span in about_section.first.locator("span").all():
                try:
                    text = span.inner_text().strip()
                    if len(text) > 50:
                        return text
                except Exception:
                    continue
    except PlaywrightTimeoutError:
        pass
    return ""
