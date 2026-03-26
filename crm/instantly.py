"""Instantly API client — implements LeadSource."""

import os
import httpx
from dotenv import load_dotenv

from crm.base import LeadSource
from crm import db

load_dotenv()

INSTANTLY_LEADS_URL = "https://api.instantly.ai/api/v2/leads/list"


class InstantlyClient(LeadSource):

    def __init__(self):
        self.api_key = os.getenv("INSTANTLY_API_KEY")
        self.headers = {"Authorization": f"Bearer {self.api_key}"}

    def fetch_leads(self) -> list[dict]:
        """Fetch all contacted leads from Instantly, sorted by last contact date."""
        leads = []
        starting_after = None

        while True:
            payload = {"limit": 100}
            if starting_after:
                payload["starting_after"] = starting_after
            resp = httpx.post(INSTANTLY_LEADS_URL, headers=self.headers, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            for lead in data.get("items", []):
                if lead.get("timestamp_last_contact"):
                    leads.append(lead)
            next_cursor = data.get("next_starting_after")
            if not next_cursor:
                break
            starting_after = next_cursor

        leads.sort(key=lambda l: l.get("timestamp_last_contact", ""), reverse=True)
        return leads

    def sync_leads(self):
        """
        Pull all contacted leads from Instantly and upsert into the leads table.
        Never overwrites linkedin_status — only updates contact info.
        """
        db.init_db()
        leads = self.fetch_leads()
        for lead in leads:
            email = lead.get("email")
            if not email:
                continue
            db.upsert_lead(
                email=email,
                first_name=lead.get("first_name") or lead.get("firstName"),
                last_name=lead.get("last_name") or lead.get("lastName"),
                linkedin_url=extract_linkedin_url(lead),
                company=lead.get("company") or lead.get("companyName"),
                source="instantly",
            )
        print(f"Synced {len(leads)} lead(s) from Instantly.")


def extract_linkedin_url(lead: dict) -> str | None:
    """Try common field names for a LinkedIn URL in a lead dict."""
    for field in ("linkedin_url", "linkedinUrl", "linkedin", "LinkedIn URL"):
        val = lead.get(field) or lead.get("variables", {}).get(field)
        if val and "linkedin.com" in val:
            return val.strip()
    val = lead.get("payload", {}).get("linkedIn")
    if val and "linkedin.com" in val:
        return val.strip()
    return None
