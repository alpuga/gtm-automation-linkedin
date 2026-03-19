"""
One-time script to log into LinkedIn and save the browser session.
Run this once before using main.py.
"""

import os
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

SESSION_FILE = os.getenv("LINKEDIN_SESSION_FILE", "linkedin_session.json")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-infobars",
                "--window-size=1366,768",
            ]
        )
        context = browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="America/New_York",
        )
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = context.new_page()

        page.goto("https://www.linkedin.com/login")
        print("Please log in to LinkedIn in the browser window.")
        print("Waiting for you to reach the feed...")

        # Wait until redirected to feed after login
        page.wait_for_url("**/feed/**", timeout=120_000)

        context.storage_state(path=SESSION_FILE)
        print(f"Session saved to {SESSION_FILE}")

        browser.close()


if __name__ == "__main__":
    main()
