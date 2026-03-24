"""Browser launch helper shared across all LinkedIn workflows."""

from config import SESSION_FILE


def launch_browser(p):
    """Launch Chromium with anti-detection settings. Returns (browser, context, page)."""
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
        storage_state=SESSION_FILE,
        viewport={"width": 1366, "height": 768},
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        locale="en-US",
        timezone_id="America/New_York",
    )
    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    page = context.new_page()
    return browser, context, page
