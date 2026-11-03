"""Tracks which refunds have already been seen, to support new-refund notifications.

This module only detects and describes new refunds - it doesn't send anything
itself (there's no email/SMTP capability in the CLI tool). track_refunds.py
writes the result to a JSON file that the calling agent (or any other
automation) reads to decide whether to notify someone.
"""

import json
import os

import pandas as pd

from actblue_refunds.dashboard import _form_category, _matches_allowed_form
from actblue_refunds.report import find_column


def _refund_id_col(df):
    return find_column(df, ["refund id"])


def load_state(state_path):
    """Returns None if no state file exists yet (first run), else
    (seen_ids, seen_accounts).

    The original format was a bare JSON list of refund ids. It is still
    read: every account in that case counts as already tracked (None).
    """
    if not os.path.exists(state_path):
        return None
    with open(state_path) as f:
        raw = json.load(f)
    if isinstance(raw, list):
        return set(map(str, raw)), None
    return set(map(str, raw.get("ids", []))), set(raw.get("accounts", []))


def load_seen_ids(state_path):
    state = load_state(state_path)
    return None if state is None else state[0]


def save_state(state_path, ids, accounts):
    with open(state_path, "w") as f:
        json.dump({"accounts": sorted(accounts), "ids": sorted(ids)}, f, indent=0)


def find_new_refunds(df, state_path):
    """Returns (new_df, bootstrapped); updates the state file as a side effect.

    On the first run (no state file yet), every current refund is recorded as
    seen but none are reported as new - there's nothing to notify about
    retroactively for refunds that already existed before tracking started.

    The same applies per account: the first time an account shows up (e.g.
    its credentials were just added), its existing refunds become its
    baseline instead of all being reported as new at once.
    """
    id_col = _refund_id_col(df)
    if id_col is None:
        return df.iloc[0:0], False

    ids = df[id_col].astype(str).where(df[id_col].notna())
    current_ids = set(ids.dropna())
    current_accounts = set(df["account"].dropna()) if "account" in df.columns else set()

    state = load_state(state_path)
    bootstrapped = state is None
    previous_ids, previous_accounts = (set(), set()) if state is None else state
    if previous_accounts is None:
        previous_accounts = set(current_accounts)

    if bootstrapped:
        new_df = df.iloc[0:0]
    else:
        mask = ids.notna() & ~ids.isin(previous_ids)
        if "account" in df.columns:
            mask &= df["account"].isin(previous_accounts)
        new_df = df[mask]

    save_state(state_path, current_ids | previous_ids, current_accounts | previous_accounts)
    return new_df, bootstrapped


def summarize_new_refunds(new_df, amount_col):
    """Describes new refunds as plain dicts, restricted to the same tracked
    form categories (text/rtext/email/ads) the dashboard shows - a refund
    from an untracked form isn't on the dashboard, so it shouldn't trigger
    a notification either.
    """
    if not len(new_df) or amount_col is None:
        return []

    form_col = find_column(new_df, ["fundraising page"])
    date_col = find_column(new_df, ["refund date"])
    first_name_col = find_column(new_df, ["donor first name"])
    last_name_col = find_column(new_df, ["donor last name"])

    if form_col is not None:
        new_df = new_df[new_df[form_col].apply(_matches_allowed_form)]

    summaries = []
    for _, row in new_df.iterrows():
        summaries.append(
            {
                "account": row.get("account"),
                "amount": float(row[amount_col]) if pd.notna(row.get(amount_col)) else None,
                "refund_date": str(row[date_col]) if date_col and pd.notna(row.get(date_col)) else None,
                "form": _form_category(row[form_col]) if form_col and pd.notna(row.get(form_col)) else None,
                "donor_first_name": row.get(first_name_col) if first_name_col else None,
                "donor_last_name": row.get(last_name_col) if last_name_col else None,
            }
        )
    return summaries
