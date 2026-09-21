# Email Grievance Classification — Context Handoff (2026-09-21)

## What this feature is
Extends MCL Patr's document pipeline to also classify incoming Gmail
correspondence — not just scanned physical documents — as Grievance /
Non-Grievance, giving every email a formal record exactly like a scanned
document gets, without building a parallel pipeline.

## Current status: built, tested, working — NOT deployed to production
Everything below runs successfully today, but only against a **local**
backend (Render usage limit is exhausted; renewal expected "next week" as
of when this started). Nothing here has been merged to `main`.

## Branch and commits
- Branch: `feature/aarushi-email-grievance-classification`, pushed to
  `origin` (https://github.com/suchitnagarnigam-star/mcl-daak.git).
- 10 commits, each a real logical step (not squashed), no Claude
  attribution lines (per explicit user request). Latest commit: `6e4dbbf`.
- `main` is completely untouched.
- No PR opened yet (not needed until ready to merge — no CI configured
  on this repo anyway).

## Architecture (final design)
```
Gmail (commissionermcl@gmail.com forwards to suchitnagarnigam@gmail.com)
  → Gmail filter auto-applies label "MCL-Grievance-Input" to matching mail
  → Apps Script (docs/apps-script/gmail-grievance-classifier.gs) polls
    for that label, calls backend POST /classify-email/
  → backend/app/routes/email.py:
      - dedup check via message_id (find_submission_by_message_id)
      - claude_service.process_document() — REUSED UNMODIFIED from the
        OCR flow, fed a synthetic "From/Subject/Date + body" text blob
      - insert_data() — REUSED, generates same MCL/{year}/{n} serial number
      - push_to_sheets() — REUSED, pushes into DAAK Records
  → Apps Script labels the Gmail thread Grievance/Non-Grievance +
    AutoClassified, but ONLY on backend HTTP 200 (full success)
  → existing, UNMODIFIED syncGrievances() (bound to DAAK Records,
    external, not in this repo) mirrors grievance-category rows into
    Grievances Data on its own schedule
```

Key design decisions and why:
- **Every email gets a DAAK Records row, grievance or not** — explicit
  user requirement, mirrors how every scanned document is logged
  regardless of category.
- **Never write to Grievances Data directly** — `syncGrievances()`
  (source pasted into `docs/apps-script/sync-grievances.gs` for
  reference) does a full clear-and-rewrite of that sheet every run, so
  anything written there directly would be wiped.
- **`message_id`-based dedup** — new nullable, `UNIQUE` Supabase column
  (`ALTER TABLE document_submission ADD COLUMN message_id text UNIQUE;`
  — already run against the real Supabase project). `insert_data()`
  takes an optional `message_id` param, backward-compatible; OCR flow
  callers unaffected.
- **Label-gating (`MCL-Grievance-Input`)** — the destination mailbox
  receives OTHER mail too, not just forwarded office correspondence, so
  the Apps Script only ever touches messages carrying this label. In
  production, a **Gmail filter** (From: `commissionermcl@gmail.com` →
  apply label) does this automatically — no manual labeling needed
  day-to-day. This filter has been set up on `suchitnagarnigam@gmail.com`.
- **Only "Public Grievance" (exact category, case-insensitive substring
  match on "grievance") reaches Grievances Data** — confirmed via
  `sync-grievances.gs`'s actual logic. Other categories (e.g. "Building
  Plan & Construction") can be genuine citizen complaints but won't
  appear there — a pre-existing quirk of that script, not something we
  introduced or can fix without touching a script we're not modifying.

## Files changed (all on the feature branch)
- `backend/app/schemas/email.py` (new) — `EmailIngestRequest`/`Response`
- `backend/app/routes/email.py` (new) — the `/classify-email/` endpoint
- `backend/app/services/supabase_service.py` (extended) — `message_id`
  param on `insert_data()`, new `find_submission_by_message_id()`
- `backend/app/main.py`, `backend/.env.example` (small wiring changes)
- `docs/apps-script/gmail-grievance-classifier.gs` (new) — the Gmail
  poller, NOT deployed by git (pasted manually into script.google.com)
- `docs/apps-script/sync-grievances.gs` (new) — verbatim reference copy
  of the user's existing, already-deployed script (not modified by us)

## Manual setup already done (outside this repo)
- Supabase: `message_id` column added + `UNIQUE` constraint, with a
  `document_submission_backup_20260916` snapshot table taken first.
- Gmail filter on `suchitnagarnigam@gmail.com`: From
  `commissionermcl@gmail.com` → apply label `MCL-Grievance-Input`.
- Apps Script project created under `suchitnagarnigam@gmail.com`,
  pasted with the script above, authorized, **automatic trigger
  installed** (`installTrigger()` was run — checks every 30 minutes).
- Local test env: `backend/.env` and `backend/app/.env` (git-ignored,
  both needed — see gotcha below) filled in with real credentials.

## Real production data has already flowed through this
Multiple real forwarded grievances (water supply, sewage, encroachment,
etc.) have been successfully classified, inserted into the **real**
Supabase table and **real** DAAK Records sheet, with correct sender
extraction even through multi-hop forwarding chains. This is genuinely
live, not just a test — treat the Supabase table and DAAK Records as
containing real operational data from here on, not just test rows.

## Currently blocking
1. **Anthropic API credits exhausted** (as of ~2026-09-19/20) — every
   classification call fails with `anthropic.BadRequestError: ... credit
   balance is too low`. Safe failure mode (no data written, no
   duplicates, threads just stay unlabeled and retry automatically once
   credits are added) but nothing new gets classified until fixed.
   Discussed a possible free fallback: `google-genai`/Gemini is already
   a dependency and partially wired in `config.py` (unused on the main
   path) and has a real free tier — switching `claude_service.py`'s
   extraction to Gemini was raised as a *separate future task*, not
   started.
2. **Render usage limit exhausted** — the real deployed backend
   (`mcl-daak.onrender.com`) is down; everything currently runs against
   a **local** Docker container + ngrok tunnel instead. This is fragile:
   Docker/the tunnel go down whenever the laptop sleeps/restarts (this
   has already happened multiple times) and need manual restarting.
   **As of 2026-09-21, both Docker and the tunnel are DOWN** — nothing
   will process until they're brought back up (see restart steps below).
3. **GitHub contribution graph** — commits are correctly authored/linked
   to `aarushigarg14` (verified via a public commit page — avatar+link
   present), but still not showing on the profile's contribution
   calendar as of last check. Left unresolved; user explicitly declined
   to merge to `main` just to test this. Possibly a propagation delay,
   possibly a branch-scoping nuance in GitHub's graph algorithm that
   wasn't fully confirmed either way.

## How to bring the local environment back up
```bash
# 1. Open Docker Desktop (from Start menu), wait for it to fully start.

# 2. Start the backend container
cd backend
docker compose up -d

# 3. Start the tunnel (has consistently reused the same URL so far,
#    but free ngrok URLs CAN change on restart — check the output)
"/c/Users/LENOVO/AppData/Local/Microsoft/WinGet/Packages/Ngrok.Ngrok_Microsoft.Winget.Source_8wekyb3d8bbwe/ngrok.exe" http 8000

# 4. Verify
curl http://localhost:8000/health
curl https://basket-parrot-cleaver.ngrok-free.dev/health   # or new URL if it changed
```
If the ngrok URL changed, update `CONFIG.ENVIRONMENTS.test.BACKEND_URL`
in the Apps Script (under `suchitnagarnigam@gmail.com`) to match, or
`processInbox` will fail with a 404.

To stop cleanly later: `docker compose down` (from `backend/`) and
`taskkill //IM ngrok.exe //F` (Git Bash syntax).

## In-progress: next feature being planned (approved to write the plan,
## NOT approved to start building yet)
**Email attachments → Grievances Data.** Staff working the Grievances
Data sheet should be able to click a link to see photos/PDF/video
attached to the original grievance email. A full plan exists at
`C:\Users\LENOVO\.claude\plans\the-next-feature-im-sharded-simon.md`.
Plan mode was exited on 2026-09-21 specifically to save this handoff
doc — the user explicitly did NOT approve starting implementation at
that point. Confirm with the user before writing any attachment-feature
code.

Plan summary (see the plan file for full detail):
- Apps Script uploads real (non-inline) attachments to one Google Drive
  folder per email (`DriveApp`, no new credentials), shared
  "anyone with the link" (confirmed: personal Gmail account, no
  Workspace domain-restricted sharing option available).
- Folder link threaded through as a new `attachments_link` field:
  `EmailIngestRequest` → `llm_result` → `insert_data()` (new nullable
  Supabase column, same additive pattern as `message_id`) →
  `push_to_sheets()` (no code change needed, already spreads `**llm_result`).
- **Genuine open unknown**: whether the external Sheets-webhook Apps
  Script (behind `SHEETS_WEBHOOK_URL`, never seen its source, separate
  from `sync-grievances.gs`) auto-creates a new column for an unknown
  JSON key, or silently drops it. Plan includes a cheap empirical test
  for this (POST a synthetic payload with an extra key, check if a new
  column appears in DAAK Records) before committing to that path, with
  a fallback (append the Drive link into the existing `summary` field)
  if new fields get dropped.
- Confirmed decisions: email-attachments only (not OCR scans), all
  attachment types, one folder link per email (not multiple), exclude
  inline/embedded images.

## Known gotchas worth remembering
- `backend/app/services/mistral_ocr_services.py` calls
  `load_dotenv()` pointing at `backend/app/.env`, NOT `backend/.env`
  like everything else — a pre-existing bug, unrelated to this feature,
  but means **local testing needs a `.env` file in BOTH locations**
  (they were kept in sync manually; not committed, both git-ignored).
- Docker Compose's `env_file: .env` mechanism sidesteps that bug
  entirely (injects real env vars directly, dotenv's misdirected call
  becomes a harmless no-op) — this is why we run via `docker compose`
  rather than a bare local `uvicorn` process.
- `EMAIL_WEBHOOK_SECRET` (local test value, safe to keep using since
  it's not a real external credential):
  `e_dTtkk4pT-Dhh-1sXpXdvi75HIdtC9wjJJk6TGmGyo` — already set in
  `backend/.env`/`backend/app/.env` and pasted into the Apps Script's
  `CONFIG.BACKEND_SECRET`.
- The first real test run swept in unrelated personal inbox mail
  (LinkedIn, Facebook, GitHub notifications) before label-gating was
  added — all cleaned up from Supabase/DAAK Records afterward. This is
  why label-gating exists at all; don't remove it without re-adding
  some other safeguard.
- A `category: null` from Claude (legitimate when nothing in the
  15-category list fits) previously crashed the response with a 500
  *after* Supabase/Sheets had already succeeded — fixed by normalizing
  `category` to `"N/A"` alongside the other optional fields. Watch for
  similar "looks like it failed but actually already wrote data" cases
  if extending this response model further.

## Working-style notes for whoever (or whichever session) picks this up
- Commit at natural checkpoints during implementation, not just in one
  big commit at the end — the user explicitly asked for this. Keep
  commit titles short and in plain language (avoid long multi-paragraph
  commit bodies — the user found those hard to scan).
- Never add `Co-Authored-By: Claude` attribution lines to commits in
  this repo — explicitly declined by the user.
- Treat the Supabase project and DAAK Records/Grievances Data sheets as
  **live production data** now, not a sandbox — real complaints have
  already gone through. Be careful with test data going forward (mark
  it obviously, e.g. `"TEST - DO NOT ACTION"` subjects, and clean up
  afterward).
