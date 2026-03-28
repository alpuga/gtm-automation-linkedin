# GTM Automation — LinkedIn

Pulls contacted leads from [Instantly](https://instantly.ai) and automates LinkedIn engagement via Playwright.

**Outreach workflow:**
- Not connected → send connection request with a personalized note
- Already connected → send direct message
- Pending / other → skip

**Status workflow (run 5–7 days after outreach):**
- Accepted (1st degree) → send follow-up DM, log as `dm_sent`
- Still pending → log as `pending`
- Ignored / expired → log as `ignored`

**Sales Navigator InMail workflow:**
- Scrapes a saved Sales Navigator people list
- Sends InMails to new leads, skipping anyone already in the database
- Logs activity as `inmail_sent`

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

Create a `.env` file:
```
INSTANTLY_API_KEY=your_key_here
LINKEDIN_SESSION_FILE=linkedin_session.json
```

**3. Save your LinkedIn session (one-time)**

Opens a real browser so you can log in manually:
```bash
poetry run python setup_session.py
```

Your session is saved to `linkedin_session.json`. Keep this file private — it grants full access to your LinkedIn account.

**4. Initialize the database and sync leads (first time)**

```bash
# If migrating from the old CSV-based setup:
poetry run python migrate_csv_to_db.py

# Pull lead contact info from Instantly into the database:
poetry run python run.py sync
```

---

## Usage

```bash
# Pull latest leads from Instantly into the database
poetry run python run.py sync

# Send connection requests and DMs to new leads
poetry run python run.py outreach

# Check invite statuses and send follow-up DMs to accepted connections
poetry run python run.py status

# Print a summary of all activity
poetry run python run.py report
```

**Options:**
```bash
poetry run python run.py outreach --dry-run                  # detect states, send nothing
poetry run python run.py outreach --profile <url> --dry-run  # test a single profile
poetry run python run.py outreach --reset-today              # reset daily limit
poetry run python run.py status --dry-run
poetry run python run.py status --inbox                      # faster: scan inbox to find acceptances instead of visiting each profile
poetry run python run.py status --inbox --dry-run
poetry run python run.py status --limit 5                    # test against first 5 leads
poetry run python run.py inmail --list <sales_nav_list_url>  # send InMails from a Sales Navigator list
poetry run python run.py inmail --list <url> --dry-run
poetry run python run.py inmail --list <url> --preview --limit 1
```

**Typical weekly rhythm:**
- Run `sync` + `outreach` daily (up to 40 leads/day)
- Run `status --inbox` once or twice a week to follow up on acceptances
- Run `report` for a snapshot at any time
- Run `inmail` separately for cold Sales Navigator outreach (10/day limit)

---

## Message Templates

All message templates live in `config.py`:

| Constant | When it's sent |
|---|---|
| `CONNECT_NOTE` | With the connection request |
| `DM_TEXT` | To leads already connected (1st degree) |
| `FOLLOW_UP_DM` | When a connection request is accepted |
| `INMAIL_SUBJECT` | Subject line for Sales Navigator InMails |
| `INMAIL_BODY` | Body for Sales Navigator InMails |

`{first_name}` is interpolated from the lead's data in the database.

---

## Project Structure

```
config.py              ← message templates, limits, file paths
run.py                 ← CLI entry point
setup_session.py       ← one-time LinkedIn login
migrate_csv_to_db.py   ← one-time migration from legacy CSV

linkedin/              ← browser automation (no business logic)
  browser.py           ← launch browser with anti-detection settings
  connect.py           ← connection request sending + state detection
  inbox.py             ← inbox scraper for finding accepted connections
  inmail.py            ← Sales Navigator InMail sending
  message.py           ← DM sending with connection degree check
  sales_nav.py         ← Sales Navigator list scraper
  scraper.py           ← pending invitations page scraper (utility)
  utils.py             ← shared page helpers

crm/                   ← data layer (no Playwright)
  base.py              ← abstract interfaces (LeadSource, ActivityLogger)
  db.py                ← SQLite layer (leads + activity_log tables)
  instantly.py         ← Instantly API client
  leads.py             ← data access interface used by workflows

workflows/             ← orchestration (imports from linkedin/ and crm/)
  outreach.py          ← send connection requests and DMs
  check_status.py      ← check invite statuses, send follow-up DMs
  sales_nav_outreach.py ← scrape Sales Navigator list and send InMails
  report.py            ← print activity summary

data/                  ← runtime artifacts (gitignored)
  leads.db             ← SQLite database (leads + activity history)
  activity_log.csv     ← legacy CSV (kept for reference)
  screenshots/         ← debug screenshots on errors
```

---

## Notes

- LinkedIn has no public API — this automates a real browser via Playwright.
- Random delays are added between profiles to reduce detection risk.
- The degree check in `linkedin/message.py` ensures follow-up DMs are never sent as InMails — only 1st-degree connections receive them.
- `status --inbox` matches accepted connections by full name from the inbox conversation list, which is faster than visiting each profile individually.
- Sales Navigator InMail leads are stored with a synthetic email key (`sn_{slug}@salesnav.local`) since they have no real email in the DB.
- `linkedin_session.json`, `.env`, and `data/` are gitignored.
