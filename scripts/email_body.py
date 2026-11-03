"""Builds the new-refunds email from new_refunds.json.

Prints JSON {"send": bool, "subject": str, "body": str}. send is false on the
baseline run or when nothing is new.

Usage: python scripts/email_body.py new_refunds.json DASHBOARD_URL
"""

import json
import sys


def _money(amount):
    return "?" if amount is None else f"${amount:,.2f}"


def build(data, dashboard_url):
    refunds = data.get("new_refunds") or []
    if data.get("bootstrapped") or not refunds:
        return {"send": False, "subject": "", "body": ""}

    refunds = sorted(refunds, key=lambda r: (r.get("account") or "", r.get("refund_date") or ""))
    blocks = []
    for r in refunds:
        donor = " ".join(p for p in (r.get("donor_first_name"), r.get("donor_last_name")) if p and str(p) != "nan")
        date = (r.get("refund_date") or "?")[:10]
        blocks.append(
            f"{r.get('account') or '?'}\n"
            f"{_money(r.get('amount'))} · {date} · form: {r.get('form') or '?'}\n"
            f"Donor: {donor or '?'}"
        )
    body = "\n\n".join(blocks) + f"\n\nDashboard: {dashboard_url}"
    return {"send": True, "subject": f"{len(refunds)} new ActBlue refund(s)", "body": body}


def main():
    with open(sys.argv[1]) as f:
        data = json.load(f)
    print(json.dumps(build(data, sys.argv[2]), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
