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

    # status
    p_status = sub.add_parser("status", help="Check invite statuses, send follow-up DMs, log pending")
    p_status.add_argument("--dry-run", action="store_true", help="Detect states but send nothing")
    p_status.add_argument("--preview", action="store_true", help="Fill message in compose box but do not send")
    p_status.add_argument("--limit", type=int, help="Only check this many leads (useful for testing)")
    p_status.add_argument("--profile", type=str, help="Test against a single LinkedIn profile URL")

    # sync
    sub.add_parser("sync", help="Pull latest leads from Instantly into the database")

    # report
    sub.add_parser("report", help="Print a summary of all activity")

    args = parser.parse_args()

    if args.command == "outreach":
        from workflows.outreach import run
        run(dry_run=args.dry_run, profile_url=args.profile, reset_today=args.reset_today)

    elif args.command == "status":
        from workflows.check_status import run
        run(dry_run=args.dry_run, preview=args.preview, limit=args.limit, profile_url=args.profile)

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
