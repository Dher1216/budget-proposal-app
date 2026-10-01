# Provincial Budget Proposal System

A multi-user web application for collecting, reviewing, and approving budget
proposals across offices, then exporting the final report to Excel.

## What's included

- **Backend**: FastAPI + SQLite (Python), with all the business logic:
  logins, roles, per-office data isolation, proposal drafts/submission,
  admin approval, and Excel export.
- **Frontend**: plain HTML/CSS/JS (no build step) — an admin dashboard and
  a per-office client portal, served by the same backend.
- **Seeded chart of accounts**: Personal Services, Maintenance and Other
  Operating Expenditures, Capital Outlay, and Financial Expenses, using the
  account codes/names you provided.
- **Default admin login**: username `Dher`, password `Derps1216`.

## How the roles work

- **Admin** (`Dher`, plus any other admins you create) can see every office,
  every year, both annual and supplemental proposals; can add offices,
  accounts, and users; enters **Previous Year Actual** and **Adjusted
  Proposal** (with its own remarks) for every line, always — independent of
  submission/approval status; and fills in the **Approved** amount, which
  locks once saved until admin clicks "Reopen approved amounts."
- **Client/office users** can only see and edit their own office's data.
  They fill in Current Annual, any number of Current-Year Supplemental
  columns (via "+ Add current-year supplemental column"), Proposed Amount,
  Remarks for Proposal, and attach supporting documents — then submit. Once
  submitted, the proposal locks until the office (or admin) reopens it.
  Previous Year Actual, Adjusted Proposal, and its remarks are admin-only
  and shown read-only to the office.
- **Two independent locks**: submitting/reopening (office-controlled, or
  admin can reopen it for them) and approving/reopening approval
  (admin-controlled) are completely separate — one never affects the other.
- **Offline behavior**: once a user has loaded a proposal or report while
  online, that data is cached on their device and will still display with
  no connection. Saving, submitting, approving, and downloading Excel files
  all require an active connection.

## Key features

- **Proposals & Reports** — per-office entry and admin review, with dynamic
  column labels based on the selected year (e.g. a 2027 proposal shows
  "2025 Actual", "Current Year 2026", "2026 Supplemental Budget No.1/No.2/...",
  "2026 Total").
- **Summary Report** (admin) — consolidated totals per account across every
  office's proposal for a budget cycle, downloadable to Excel.
- **Running Balance** (admin) — shown wherever a proposal/report/summary is
  loaded: Available Budget, Total Proposed (all offices), Available Balance
  vs Total Proposed, Total Adjusted (all offices), and Available Balance vs
  Adjusted Proposal — negative balances show in red, positive in blue.
- **Account proration tool** (admin, in the Funding tab) — for accounts like
  "Other General Services" or "Other Professional Services" (Job Order /
  Contract of Service salaries), preview and apply a month-based reduction
  (e.g. fund only 6 of 12 months) across every office at once. Writes into
  each office's Adjusted Proposal, leaving the original Proposed amount and
  any already-Approved amount untouched.
- **Fund Sources** (admin) — track available income per budget cycle, with
  a one-click "Add standard fund sources" button pre-loaded with the
  province's usual income line items.
- **Backup & Cleanup** (admin) — download everything (including attached
  files) as one .zip, delete a year's attachments to free up space, or
  permanently purge an entire old year (type-to-confirm required).
- **Activity log** — every save, submit, reopen, approval, and admin-field
  change is recorded with who did it and when.
- **Logos** — admin can upload a login-screen logo, a default/province logo
  (used as the automatic fallback), and a logo per office (Offices tab).
  Logos appear on the left side of Proposals, Reports, Summary Report, and
  the office's own proposal view.
- **Print button** (Reports tab) — prints a clean copy with the logo and
  office name at the top, no navigation or buttons.
- **Comma-formatted number entry** — every amount field displays and accepts
  commas as you type (e.g. 1,234,567.89) to make large numbers easier to
  enter correctly; values are still stored as plain numbers.
- **Supporting documents** — PDF only, capped at 8 MB per file.
- **Special Purpose Appropriations** (Funding tab) — the 20% Development
  Fund and 5% LDRRMF compute automatically from your fund sources; Aid to
  Barangays defaults to ₱590,000 and is editable; add other one-off
  deductions as needed. These are deducted from Available Budget before
  offices are allocated anything, same as in the real budget process.
- **LBP Form 1 export** (Summary Report tab) — the full "Budget of
  Expenditures and Sources of Financing" report: fund sources by category,
  office expenditures by classification, SPA deductions, and the resulting
  ending balance, all in one document. Note: unlike the original government
  template, this doesn't split the current year into semesters (Actual/
  Estimate) — the app only tracks a single current-year total.
- **Fund source editing** — all amounts save together via one "Save all
  amounts" button, so editing several rows and saving once can never wipe
  another row's unsaved edit. The two auto-computed SPA deductions also
  show a live preview as you type, before you save anything.
- **Summary Report now shows Fund Sources** alongside Expenditures.
- **Formal report headings** — Proposals, Reports, Summary Report, and the
  office's own view now show a proper heading (e.g. "ANNUAL BUDGET 2027")
  with the office name as a subtitle, instead of one small line of text.
- **Password reset** (Users tab) — admin can set a new password for any
  user at any time. Note: there's no way to view a user's *existing*
  password — passwords are stored as one-way hashes (the secure standard),
  which can't be reversed into the original text. Resetting to a new known
  password is the secure equivalent.
- **Offline editing for admin** (Proposals tab) — click "Lock for admin
  editing" on a proposal to prevent the office from editing it, then every
  field (including the office's own) becomes editable by admin, including
  with no internet connection — useful during a budget hearing with poor
  signal. Edits made offline are saved on your device and sync
  automatically once you're back online (or click "Sync now"). Attached
  PDFs are cached for offline viewing once opened while online. This is
  designed for a single admin device working on a locked proposal at a
  time — locking it first is what keeps this safe, since the office can't
  make conflicting edits while you're working on it.
- **Bulk lock/unlock** (Proposals tab) — lock or unlock every office's
  existing proposal for a given year/budget type/supplemental number at
  once, instead of one office at a time — handy right before and after a
  hearing day. Only affects offices that have actually started a proposal
  for that cycle.
- **The app loads with zero internet connection** (not just intermittent —
  genuinely no signal, including after a laptop restart or the browser
  being fully closed and reopened). After visiting the app once while
  online, a service worker keeps a local copy of its own pages, so
  reopening it later works even with no connection at all — combined with
  the offline write-queue and cached attachments, this means a full
  multi-day disconnected work session (e.g. a budget hearing with no
  signal) is genuinely supported, not just brief drops. **If you update
  this app in the future**, remember to bump `CACHE_VERSION` in
  `frontend/sw.js` to match the `?v=...` value used in the HTML files —
  otherwise offline users stay stuck on the old cached version.

## Running it locally (to try it out)

You'll need Python 3.10+.

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python seed_data.py             # creates budget.db, loads accounts + admin user
uvicorn main:app --reload
```

Then open **http://localhost:8000** in a browser (desktop or phone on the
same network, using your computer's local IP instead of `localhost`) and
sign in with `Dher` / `Derps1216`.

## Deploying so 30+ offices can reach it over the internet — for free

Render's free web service works fine for hosting the app itself, but its
local disk is wiped every time it restarts or redeploys — so anything
written to a local file (like a SQLite database) disappears. The fix isn't
to pay Render — it's to keep your actual data somewhere that doesn't get
wiped, and let Render's free tier just run the app.

**This app is already set up for that:**
- All uploaded supporting documents are stored as bytes *inside* the
  database (not as separate files on disk) — see `backend/models.py`. So as
  long as the database itself is persistent, attachments are too.
- The database connection is controlled by one environment variable
  (`DATABASE_URL`), so switching from local SQLite to an external Postgres
  needs zero code changes.

**The free setup:**

1. **Create a free Postgres database at [Neon](https://neon.tech)** (or
   [Supabase](https://supabase.com) — either works). Neon's free tier has no
   expiration date and needs no credit card, unlike Render's own free
   Postgres, which is deleted after 30 days.
2. Copy the connection string Neon gives you (it looks like
   `postgresql://user:password@ep-xxxx.neon.tech/dbname?sslmode=require`).
3. **Deploy the backend to Render's free web service** (GitHub upload →
   Render, as covered earlier in this conversation). In Render's
   Environment Variables section, add:
   - `DATABASE_URL` = the Neon connection string from step 2
   - `BUDGET_APP_SECRET_KEY` = any long random string (used to sign login
     sessions)
4. Set the Build Command to:
   `pip install -r requirements.txt psycopg2-binary && python seed_data.py`
   (`psycopg2-binary` is the Postgres driver — it's only added here, at
   deploy time on Render's Linux environment, not in `requirements.txt`
   itself, because some Windows Python versions fail to install it locally
   with a confusing "pg_config not found" error that has nothing to do with
   your setup. Render's Linux servers install it without any issue.)
5. Deploy. The app now runs on Render's free tier, but all its data —
   proposals, accounts, users, and attachments — lives permanently in Neon,
   so nothing is lost when Render restarts or redeploys the service.

**What this setup still doesn't give you** (this is true of any free tier,
not just this app): no uptime guarantee, the free web service "spins down"
after inactivity so the first request after a quiet period takes ~30-60
seconds to wake up, and Neon's free tier has modest storage/compute limits
that are generous for this use case but not unlimited. If the system
becomes critical to daily operations, upgrading Render's compute plan (and
possibly Neon's) removes the cold-start delay and raises those ceilings —
but you're not required to do that just to avoid data loss anymore.

**Before going live with real data either way:**
- Change the default admin password after first login.
- Set a real `BUDGET_APP_SECRET_KEY` environment variable (used to sign
  login tokens) instead of the default placeholder in `backend/auth.py`.
- Restrict CORS in `backend/main.py` (`allow_origins`) to your real domain
  once you know it, instead of `"*"`.
- Take regular backups — Neon supports point-in-time recovery even on the
  free tier, but it's worth confirming your retention window.

## Project structure

```
backend/
  main.py           FastAPI app & all API routes
  models.py         Database tables
  schemas.py        API request/response shapes
  auth.py           Login, password hashing, JWT sessions
  database.py       DB connection (SQLite by default)
  seed_data.py       Loads the chart of accounts + default admin
  excel_export.py   Builds the downloadable .xlsx report
  requirements.txt
frontend/
  index.html        Login screen
  admin.html / js/admin.js     Admin dashboard (Proposals, Reports, Accounts, Offices, Users tabs)
  client.html / js/client.js   Office portal (fill in & submit proposals)
  js/api.js         Shared API + offline-caching helper
  css/app.css
```

## Notes on the account codes

A few codes are intentionally shared by more than one account name (e.g.
`50101010` for both "Salaries & Wages-Regular" and its "Step Increment"
variant). These are treated as valid sibling entries — sorting falls back
to account name when codes match.

## Extending later

- The **Add Account** feature (admin → Accounts tab) lets you add new
  account codes/names under any classification at any time; new accounts
  automatically appear (at zero) in every office's future proposals.
- The **Add Office** feature (admin → Offices tab) lets you onboard new
  offices without touching code.
- To assign a client user, first create the office, then create the user
  with role "Client" and pick that office.
