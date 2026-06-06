"""Single CLI entry point for all LinkedIn automation workflows."""

import argparse
import os

from dotenv import load_dotenv
load_dotenv()


def main():
    parser = argparse.ArgumentParser(prog="run", description="LinkedIn automation")
    sub = parser.add_subparsers(dest="command")

    # outreach
    p_out = sub.add_parser("outreach", help="Send connection requests and DMs to new leads")
    p_out.add_argument("--dry-run", action="store_true", help="Detect states but send nothing")
    p_out.add_argument("--profile", type=str, help="Test against a single LinkedIn profile URL (requires --dry-run)")
    p_out.add_argument("--reset-today", action="store_true", help="Remove today's entries to reset the daily limit")
    p_out.add_argument("--from-db", action="store_true", help="Read uncontacted leads from local DB instead of Instantly API")
    p_out.add_argument("--campaign", type=str, help="Only send to leads in this campaign")
    p_out.add_argument("--min-score", type=int, help="Skip leads scored below this threshold (default: no filter)")

    # status
    p_status = sub.add_parser("status", help="Check invite statuses, send follow-up DMs, log pending")
    p_status.add_argument("--dry-run", action="store_true", help="Detect states but send nothing")
    p_status.add_argument("--preview", action="store_true", help="Fill message in compose box but do not send")
    p_status.add_argument("--limit", type=int, help="Only check this many leads (useful for testing)")
    p_status.add_argument("--profile", type=str, help="Test against a single LinkedIn profile URL")
    p_status.add_argument("--inbox", action="store_true", help="Scan inbox to find accepted connections instead of visiting each profile")

    # inmail
    p_inmail = sub.add_parser("inmail", help="Scrape a Sales Navigator list and send InMails")
    p_inmail.add_argument("--list", type=str, help="Sales Navigator people list URL")
    p_inmail.add_argument("--profile", type=str, help="Test against a single Sales Navigator profile URL")
    p_inmail.add_argument("--dry-run", action="store_true", help="Detect leads but send nothing")
    p_inmail.add_argument("--preview", action="store_true", help="Fill InMail compose but do not send")
    p_inmail.add_argument("--limit", type=int, help="Only process this many leads")

    # scrape
    p_scrape = sub.add_parser("scrape", help="Scrape a Sales Navigator list and save leads to DB")
    p_scrape.add_argument("--list", type=str, required=True, help="Sales Navigator people list URL")
    p_scrape.add_argument("--campaign", type=str, help="Campaign name — required for new lists (e.g. founders, investors, users)")
    p_scrape.add_argument("--name", type=str, help="Override list name (auto-detected from page by default)")
    p_scrape.add_argument("--dry-run", action="store_true", help="Detect leads but save nothing")
    p_scrape.add_argument("--limit", type=int, help="Only process this many new leads")

    # lists
    sub.add_parser("lists", help="Show all scraped lists with lead counts")

    # leads
    p_leads = sub.add_parser("leads", help="Inspect leads stored in the DB")
    p_leads.add_argument("--campaign", type=str, help="Filter by campaign")
    p_leads.add_argument("--list", type=str, help="Filter by list name")
    p_leads.add_argument("--status", type=str, help="Filter by linkedin_status")

    # score
    p_score = sub.add_parser("score", help="Score leads using Claude AI against campaign ICP")
    p_score.add_argument("--campaign", type=str, help="Filter by campaign")
    p_score.add_argument("--limit", type=int, help="Only score this many leads")
    p_score.add_argument("--rescore", action="store_true", help="Re-score leads that already have a score")

    # sync
    sub.add_parser("sync", help="Pull latest leads from Instantly into the database")

    # report
    sub.add_parser("report", help="Print a summary of all activity")

    args = parser.parse_args()

    if args.command == "outreach":
        from workflows.outreach import run
        run(dry_run=args.dry_run, profile_url=args.profile, reset_today=args.reset_today, from_db=args.from_db, campaign=args.campaign, min_score=args.min_score)

    elif args.command == "status":
        from workflows.check_status import run
        run(dry_run=args.dry_run, preview=args.preview, limit=args.limit, profile_url=args.profile, inbox=args.inbox)

    elif args.command == "inmail":
        from workflows.sales_nav_outreach import run
        if not args.list and not args.profile:
            print("Error: provide --list <url> or --profile <url>")
        else:
            run(list_url=args.list, dry_run=args.dry_run, preview=args.preview, limit=args.limit, profile_url=args.profile)

    elif args.command == "scrape":
        from workflows.scrape import run
        run(list_url=args.list, campaign=args.campaign, name=args.name, dry_run=args.dry_run, limit=args.limit)

    elif args.command == "leads":
        from crm.db import get_connection, init_db
        init_db()
        filters, params = [], []
        if args.campaign:
            filters.append("l.campaign = ?")
            params.append(args.campaign)
        if args.list:
            filters.append("li.name LIKE ?")
            params.append(f"%{args.list}%")
        if args.status:
            filters.append("l.linkedin_status = ?")
            params.append(args.status)
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        with get_connection() as conn:
            rows = conn.execute(f"""
                SELECT l.first_name, l.last_name, l.title, l.company,
                       l.location, l.headline, l.bio, l.linkedin_url, l.linkedin_status,
                       l.campaign, l.score, l.score_reason, l.persona, li.name as list_name
                FROM leads l
                LEFT JOIN lists li ON li.id = l.list_id
                {where}
                ORDER BY l.created_at DESC
            """, params).fetchall()
        if not rows:
            print("No leads found.")
        else:
            print(f"{len(rows)} lead(s)\n")
            for r in rows:
                r = dict(r)
                name = f"{r['first_name'] or ''} {r['last_name'] or ''}".strip() or "Unknown"
                print(f"  {name}  —  {r['title'] or '?'} @ {r['company'] or '?'}")
                if r["location"]:
                    print(f"    location  : {r['location']}")
                if r.get("headline"):
                    print(f"    headline  : {r['headline'][:120]}")
                if r["linkedin_url"]:
                    print(f"    linkedin  : {r['linkedin_url']}")
                score_str = f"  |  score: {r['score']}/10" if r.get("score") is not None else ""
                persona_str = f"  |  persona: {r['persona']}" if r.get("persona") else ""
                print(f"    status    : {r['linkedin_status']}  |  campaign: {r['campaign'] or '—'}  |  list: {r['list_name'] or '—'}{score_str}{persona_str}")
                if r.get("score_reason"):
                    print(f"    score note: {r['score_reason']}")
                if r["bio"]:
                    snippet = r["bio"][:120].replace("\n", " ")
                    print(f"    bio       : {snippet}{'…' if len(r['bio']) > 120 else ''}")
                print()

    elif args.command == "lists":
        from crm.db import get_all_lists
        rows = get_all_lists()
        if not rows:
            print("No lists yet. Run `python run.py scrape --list <url> --campaign <name>` to add one.")
        else:
            print(f"{'NAME':<30} {'CAMPAIGN':<14} {'LEADS':>6}  {'LAST SCRAPED'}")
            print("-" * 70)
            for r in rows:
                scraped = r["last_scraped_at"][:10] if r["last_scraped_at"] else "never"
                print(f"{r['name']:<30} {(r['campaign'] or ''):<14} {r['lead_count']:>6}  {scraped}")

    elif args.command == "score":
        from workflows.score import run
        run(campaign=args.campaign, limit=args.limit, rescore=args.rescore)

    elif args.command == "sync":
        from crm.instantly import InstantlyClient
        InstantlyClient().sync_leads()

    elif args.command == "report":
        from workflows.report import run
        run()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
