# Daily ActBlue refunds dashboard refresh

Runs every day at 11:00 UTC (`0 11 * * *`) as a scheduled task. Covers all 45
clients in `accounts.yaml`. Each run follows these steps on branch
`claude/refunds-all-45-clients` of `elizabeth747/Actblue-Refunds`.

## Before the first run

- **Google Secret Manager access.** Keys are read from the vault that
  `scripts/add-secrets.sh` fills: one secret per client named
  `actblue_<client>` (e.g. `actblue_brad-lander`) holding
  `{"client_uuid", "client_secret"}`. Set two environment variables in the
  cloud environment's settings:
  - `ACTBLUE_SECRETS_PROJECT`: the Google Cloud project ID that holds the
    secrets.
  - `GOOGLE_SERVICE_ACCOUNT_JSON`: the full JSON key of a service account
    with only the **Secret Manager Secret Accessor** role on that project.

  `ACTBLUE_<KEY>_CLIENT_UUID` / `_CLIENT_SECRET` environment variables still
  work and take priority over the vault for that client (`.env.example`
  lists the names). A client with no secret is skipped and listed in the run
  report; it doesn't stop the others.
- **Network access** to `secure.actblue.com`, added under Allowed domains in
  the environment's network settings. (Google's APIs are already reachable.)

## Steps

1. **Get the code.** If `/home/user/actblue-refunds` doesn't exist (the
   container was reclaimed), clone the repo there and check out
   `claude/refunds-all-45-clients`. Otherwise `git pull` that branch. Run
   `pip install -q -r requirements.txt`.
2. **Pull refunds.** Run
   `python track_refunds.py --months-back 6 --skip-missing-credentials --out refunds_combined.xlsx`.
   Don't compute `--start`/`--end` by hand; `--months-back` handles the
   rolling window. This writes `refunds_combined.xlsx`,
   `refunds_combined.html`, `refund_notify_state.json`, `new_refunds.json`
   and `run_status.json`.
3. **Check the run report.** Read `run_status.json`. Note every client in
   `failed` (with its error) and in `missing_credentials`; don't drop them
   silently. If the script exited without writing a dashboard (no client
   returned data), skip to step 8.
4. **Build the page.** Run
   `python scripts/make_artifact.py refunds_combined.html <scratchpad>/refunds_dashboard.html`.
   Don't hand-edit the HTML.
5. **Publish the dashboard** with the Artifact tool from that scratchpad
   file. Icon: `money`. Description: "Live refund totals and donor-level
   detail across every ActBlue client account, updated each time the
   tracker runs." If `dashboard_url.txt` exists in the repo, publish to that
   URL so the link stays the same. On the first run, write the URL the
   publish returns to `dashboard_url.txt`.
6. **Build the email.** Run
   `python scripts/email_body.py new_refunds.json <dashboard URL>`. If
   `send` is false (first run, a client's first day, or nothing new), don't
   email.
7. **Send the email** if `send` is true, with Gmail `send_message`:
   - To: elizabeth@goodmancampaigns.com
   - CC: neil@goodmancampaigns.com, jacob@goodmancampaigns.com
   - Subject and body exactly as `email_body.py` printed them: plain text,
     nothing added.
8. **Save the state.** If `git status --short refund_notify_state.json dashboard_url.txt`
   shows changes, commit only those two files and push to
   `claude/refunds-all-45-clients`. Never commit `refunds_combined.*`,
   `new_refunds.json`, `run_status.json` or `.env`. If the push is rejected,
   pull with rebase and retry once; don't force-push.
9. **Stay quiet when all is well.** If every step succeeded, don't post in
   the session. The email, when there is one, is the notification.
10. **Report problems.** If anything failed (ActBlue unreachable, a client's
    API call failing, clients with missing keys, the page build, the
    publish, the email or the push), post one message in the session saying
    exactly what failed and what's needed. List missing-key clients in one
    line, not one message each.

Donor names appear in the dashboard and the email. Never paste donor details,
API keys or anything from `.env` into commits or session messages.
