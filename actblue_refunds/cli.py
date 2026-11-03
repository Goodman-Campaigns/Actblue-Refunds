import argparse
import io
import json
import sys

import pandas as pd
import requests
from dotenv import load_dotenv

from actblue_refunds.accounts import MissingCredentialsError, load_accounts
from actblue_refunds.client import ActBlueAPIError, ActBlueClient
from actblue_refunds.dashboard import write_dashboard
from actblue_refunds.notify import find_new_refunds, summarize_new_refunds
from actblue_refunds.report import detect_columns, write_report


def rolling_window(months_back, today=None):
    """Returns (start, end) as YYYY-MM-DD strings: a `months_back`-month window
    ending tomorrow (exclusive), so it always includes today's refunds.

    Deriving start from end (rather than computing "today minus N months" and
    "tomorrow" separately) keeps the span exactly `months_back` calendar
    months, never a day over. Uses pandas' DateOffset rather than naive
    date(year, month - N, day) arithmetic, which raises ValueError outright
    for a start day that doesn't exist in the target month (e.g. Aug 31 minus
    6 months has no Feb 31) - DateOffset clamps to the month's last day
    instead.
    """
    today = pd.Timestamp.now().normalize() if today is None else pd.Timestamp(today).normalize()
    end = today + pd.Timedelta(days=1)
    start = end - pd.DateOffset(months=months_back)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Combine ActBlue refund data across multiple accounts.")
    parser.add_argument("--start", help="Start date, inclusive, YYYY-MM-DD (required unless --months-back is given)")
    parser.add_argument("--end", help="End date, exclusive, YYYY-MM-DD (required unless --months-back is given)")
    parser.add_argument(
        "--months-back",
        type=int,
        help=(
            "Instead of --start/--end, use a rolling window of this many months ending tomorrow "
            "(exclusive), so it always includes today. Handles month-end dates safely (e.g. Aug 31 "
            "minus 6 months clamps to Feb 28) - safer than computing --start by hand each day."
        ),
    )
    parser.add_argument("--config", default="accounts.yaml", help="Path to accounts config file")
    parser.add_argument("--out", default="refunds_combined.xlsx", help="Output spreadsheet path")
    parser.add_argument(
        "--dashboard-out",
        default=None,
        help="Output HTML dashboard path (default: --out with a .html extension)",
    )
    parser.add_argument("--no-dashboard", action="store_true", help="Skip generating the HTML dashboard")
    parser.add_argument(
        "--notify-state",
        default="refund_notify_state.json",
        help="Path to the new-refund tracking state file (which refund IDs have already been seen)",
    )
    parser.add_argument(
        "--new-refunds-out",
        default="new_refunds.json",
        help="Where to write newly-seen refunds as JSON, for notification tooling",
    )
    parser.add_argument("--no-notify", action="store_true", help="Skip new-refund tracking entirely")
    parser.add_argument(
        "--skip-missing-credentials",
        action="store_true",
        help=(
            "Leave out accounts whose credentials aren't set instead of stopping, and list them "
            "in --status-out. Without this flag, any missing credentials stop the run."
        ),
    )
    parser.add_argument(
        "--status-out",
        default="run_status.json",
        help="Where to write which accounts succeeded, failed, or had no credentials",
    )
    args = parser.parse_args(argv)

    if args.months_back is not None:
        if args.start is None and args.end is None:
            args.start, args.end = rolling_window(args.months_back)
        else:
            parser.error("--months-back can't be combined with --start/--end")
    elif args.start is None or args.end is None:
        parser.error("either both --start and --end, or --months-back, is required")

    return args


def main(argv=None):
    load_dotenv()
    args = parse_args(argv)

    missing = []
    try:
        if args.skip_missing_credentials:
            accounts, missing = load_accounts(args.config, skip_missing=True)
        else:
            accounts = load_accounts(args.config)
    except MissingCredentialsError as e:
        sys.exit(str(e))

    status = {"start": args.start, "end": args.end, "succeeded": [], "failed": [], "missing_credentials": missing}
    for m in missing:
        print(f"Skipping {m['name']}: missing {', '.join(m['missing'])}", file=sys.stderr)

    if not accounts:
        _write_status(args.status_out, status)
        sys.exit(f"No accounts with credentials configured in {args.config}")

    frames = []
    for account in accounts:
        print(f"Fetching refunds for {account['name']}...")
        client = ActBlueClient(account["client_uuid"], account["client_secret"])
        try:
            csv_text = client.get_refunded_contributions(args.start, args.end)
            df = pd.read_csv(io.StringIO(csv_text)) if csv_text.strip() else None
        except (ActBlueAPIError, TimeoutError, requests.RequestException, pd.errors.ParserError) as e:
            print(f"  ERROR: {e}", file=sys.stderr)
            status["failed"].append({"key": account["key"], "name": account["name"], "error": str(e)})
            continue

        if df is None or df.empty:
            status["succeeded"].append({"key": account["key"], "name": account["name"], "refunds": 0})
            print("  0 refunded contribution(s)")
            continue
        df.insert(0, "account", account["name"])
        frames.append(df)
        status["succeeded"].append({"key": account["key"], "name": account["name"], "refunds": len(df)})
        print(f"  {len(df)} refunded contribution(s)")

    _write_status(args.status_out, status)

    if not frames:
        sys.exit("No refund data retrieved for any account.")

    combined = pd.concat(frames, ignore_index=True, sort=False)
    write_report(combined, args.out)
    print(f"\nWrote combined report for {len(frames)} account(s), {len(combined)} refund(s) to {args.out}")

    if not args.no_dashboard:
        dashboard_out = args.dashboard_out or _default_dashboard_path(args.out)
        write_dashboard(combined, dashboard_out, start=args.start, end=args.end)
        print(f"Wrote dashboard to {dashboard_out}")

    if not args.no_notify:
        new_df, bootstrapped = find_new_refunds(combined, args.notify_state)
        amount_col, _ = detect_columns(combined)
        new_refunds = summarize_new_refunds(new_df, amount_col)
        with open(args.new_refunds_out, "w") as f:
            json.dump({"bootstrapped": bootstrapped, "new_refunds": new_refunds}, f, indent=2)

        if bootstrapped:
            print(f"\nEstablished refund-tracking baseline ({len(combined)} refunds) - nothing to notify about yet.")
        elif new_refunds:
            print(f"\n{len(new_refunds)} new refund(s) since last check - see {args.new_refunds_out}")
        else:
            print("\nNo new refunds since last check.")


def _write_status(path, status):
    with open(path, "w") as f:
        json.dump(status, f, indent=2)


def _default_dashboard_path(out_path):
    if out_path.lower().endswith(".xlsx"):
        return out_path[: -len(".xlsx")] + ".html"
    return out_path + ".html"


if __name__ == "__main__":
    main()
