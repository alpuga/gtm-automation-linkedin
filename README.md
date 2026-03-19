# GTM Automation — LinkedIn

Pulls contacted leads from [Instantly](https://instantly.ai) and automates LinkedIn outreach via Playwright:

- **Not connected** → sends a connection request with a personalized note
- **Already connected** → sends a direct message
- **Pending / unknown** → skips

---

## Requirements

- Python 3.11+
- [Poetry](https://python-poetry.org/)

## Setup

**1. Install dependencies**
```bash
poetry install
poetry run playwright install chromium
```

**2. Configure environment**

Copy `.env` and fill in your Instantly API key:
```bash
cp .env .env.local  # optional, or just edit .env directly
```
```
INSTANTLY_API_KEY=your_key_here
LINKEDIN_SESSION_FILE=linkedin_session.json
```

**3. Save your LinkedIn session (one-time)**

This opens a real browser so you can log in manually:
```bash
poetry run python setup_session.py
```
Your session is saved to `linkedin_session.json`. Keep this file private — it grants access to your LinkedIn account.

---

## Usage

```bash
poetry run python main.py
```

The script will:
1. Fetch all leads from Instantly that have been sent at least one email
2. Visit each lead's LinkedIn profile
3. Send a connection request or direct message based on their connection status
4. Log the result per lead (`connected` / `messaged` / `skipped` / `error`)

---

## Message Templates

Edit the templates at the top of `main.py`:

```python
CONNECT_NOTE = "Hi {first_name}, I noticed we've been in touch via email — I'd love to connect here too!"
DM_TEXT = "Hi {first_name}, great to be connected! Wanted to follow up on the email we sent over recently."
```

`{first_name}` is interpolated from the lead's data in Instantly.

---

## Project Structure

```
.
├── .env                  # API key and config (not committed)
├── linkedin_session.json # Saved browser session (not committed)
├── setup_session.py      # One-time LinkedIn login
├── main.py               # Main automation script
└── pyproject.toml        # Dependencies (Poetry)
```

---

## Notes

- LinkedIn has no public API — this uses Playwright to automate the browser.
- A random 3–7 second delay is added between each profile to reduce detection risk.
- Re-running the script will re-process all contacted leads. A processed-leads log can be added to avoid duplicates.
- `linkedin_session.json` and `.env` should be added to `.gitignore`.
