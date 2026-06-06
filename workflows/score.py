"""
Score leads using Claude — rates each lead 1-10 against the campaign ICP.
Scores are stored in the leads table and used by outreach to skip poor fits.
"""

import json
import time
import anthropic

import config
from crm import db

_PROMPT = """\
You are evaluating a LinkedIn lead for an AI calling platform sold to M&A deal sourcing teams.

Ideal customer profile:
{icp}

Lead profile:
- Name: {name}
- Title: {title}
- Company: {company}
- Headline: {headline}
- Bio: {bio}

Score this lead 1–10 on fit, and classify their persona from the options below.

Personas:
- md_partner     : Managing Director or Partner — economic buyer, signs the check
- vp_origination : VP/Director of Origination, Business Development, or Deal Sourcing — power user
- gc_compliance  : General Counsel, Chief Compliance Officer, or legal/compliance role — gatekeeper
- coo_cfo        : COO or CFO at an advisory/PE firm — budget approver
- other          : Adjacent finance role, operating company executive, or unclear fit

Scoring guide:
1–3 = poor fit — no M&A or deal sourcing exposure whatsoever (pure accounting, FP&A, treasury, or unrelated roles)
4–6 = referral potential — current role is operational (e.g. in-house CFO, COO) BUT bio or headline shows prior M&A, investment banking, PE, deal sourcing, or capital markets experience; worth a warm referral ask
7–10 = strong fit — currently active in deal sourcing, origination, or capital advisory at an advisory firm, PE firm, or M&A boutique

Respond with JSON only, no other text:
{{"score": <int 1-10>, "persona": "<one of the persona keys above>", "reason": "<one concise sentence>"}}"""


def run(campaign: str = None, limit: int = None, rescore: bool = False):
    if not config.ANTHROPIC_API_KEY:
        print("Error: ANTHROPIC_API_KEY not set in .env")
        return

    db.init_db()

    if rescore:
        # Re-score everything (or everything in campaign)
        leads = db.load_unscored_leads(campaign=campaign)
        # Also pull already-scored leads
        with db.get_connection() as conn:
            where = "WHERE linkedin_url IS NOT NULL AND linkedin_url != ''"
            params = []
            if campaign:
                where += " AND campaign = ?"
                params.append(campaign)
            rows = conn.execute(
                f"SELECT email, first_name, last_name, title, company, headline, bio, campaign FROM leads {where} ORDER BY created_at DESC",
                params
            ).fetchall()
        leads = [dict(r) for r in rows]
    else:
        leads = db.load_unscored_leads(campaign=campaign)

    if not leads:
        print("No unscored leads found.")
        return

    if limit:
        leads = leads[:limit]

    icp = config.CAMPAIGN_ICPS.get(campaign or "", "")
    if not icp:
        print(f"Warning: no ICP defined for campaign '{campaign}' in config.CAMPAIGN_ICPS.")
        print("Add one to config.py for better scoring accuracy.\n")
        icp = "Senior decision-makers at relevant companies."

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    total = len(leads)
    scored = 0
    errors = 0

    print(f"Scoring {total} lead(s) for campaign: {campaign or 'all'}\n")

    for i, lead in enumerate(leads, 1):
        name = f"{lead.get('first_name') or ''} {lead.get('last_name') or ''}".strip() or "Unknown"
        print(f"[{i}/{total}] {name} ... ", end="", flush=True)

        prompt = _PROMPT.format(
            icp=icp,
            name=name,
            title=lead.get("title") or "—",
            company=lead.get("company") or "—",
            headline=lead.get("headline") or "—",
            bio=(lead.get("bio") or "—")[:500],
        )

        try:
            message = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=256,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text.strip()
            # Extract JSON even if Claude adds preamble text
            start = raw.find("{")
            end = raw.rfind("}") + 1
            data = json.loads(raw[start:end])
            score = int(data["score"])
            reason = data.get("reason", "")
            persona = data.get("persona", "other")
            db.update_lead_score(lead["email"], score, reason, persona)
            print(f"{score}/10  [{persona}]  —  {reason}")
            scored += 1
        except Exception as e:
            print(f"error ({e})")
            errors += 1

        if i < total:
            time.sleep(0.3)  # stay well within API rate limits

    print(f"\nDone. {scored} scored, {errors} error(s).")
    print(f"Leads scoring below {config.SCORE_THRESHOLD} will be skipped by outreach.")
