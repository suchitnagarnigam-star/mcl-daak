# Email Grievance Classification — Project Context

## Overview

MCL Patr's document pipeline originally handled only physically scanned
correspondence (OCR → Claude extraction → Supabase → Google Sheets). This
feature extends the same pipeline to incoming Gmail correspondence:
emails are classified as Grievance / Non-Grievance and given a formal
record identical in shape to a scanned document, without building a
separate pipeline.

## Architecture

```
Gmail (office inbox forwards correspondence to a dedicated mailbox)
  → Gmail filter auto-applies a label to mail from the known forwarding
    address
  → Apps Script polls for that label, POSTs each message to the backend
  → Backend (POST /classify-email/):
      1. Dedup check by Gmail message_id
      2. Claude extraction (reused, unmodified, from the OCR flow) on a
         synthetic "From/Subject/Date + body" text blob
      3. Insert into Supabase (reused serial-number generation)
      4. Push to the DAAK Records Sheets webhook (reused)
  → Apps Script labels the Gmail thread (Grievance/Non-Grievance +
    Processed), but only once the backend confirms full success
  → An existing, separate Apps Script (already deployed, bound to the
    DAAK Records spreadsheet) mirrors grievance-category rows from DAAK
    Records into a dedicated Grievances sheet on its own schedule
```

## Key design decisions

- **Reuse the document pipeline rather than build a parallel one.**
  Email text is fed through the same Claude extraction function used for
  scanned documents (same 15-category list, same 9 extracted fields:
  date, subject, summary, department, category, sender_name,
  sender_contact, receiver, reference_number), the same Supabase insert
  function (same serial-number scheme), and the same Sheets webhook.
  This avoids duplicating classification logic and keeps email and
  scanned-document records structurally identical.
- **Every email gets a formal record, grievance or not** — mirrors how
  every scanned document is logged regardless of category. Only
  grievance-category records are additionally mirrored into the
  dedicated Grievances sheet.
- **Never write to the Grievances sheet directly.** The existing sync
  script that populates it rebuilds that sheet from DAAK Records on every
  run. It remembers each row's `STATUS` by Serial Number and writes it
  back, so statuses typed by staff survive; anything else written to the
  Grievances sheet directly is wiped on the next sync. Rows are copied by
  column **position**, so `STATUS` must stay to the right of every
  column that DAAK Records has (adding a DAAK Records column can collide
  with it). That sync script also only recognizes a category as a
  grievance by a substring match on the word "grievance" (excluding
  "non-grievance") — categories that are clearly complaints in plain
  English but don't contain that word (e.g. a construction/encroachment
  complaint) will not appear there, even though they're correctly
  recorded in DAAK Records.
- **Deduplication by Gmail message_id.** A nullable, unique column on
  the Supabase submissions table lets the backend detect whether a
  message has already been processed. A message already fully complete
  returns its stored result idempotently; a message that previously
  failed partway through (e.g. inserted into Supabase but failed to
  reach the Sheet) is retried only for the failed step, never
  re-inserted. This makes retries from the Gmail poller safe by
  construction — no duplicate records are possible.
- **Success is all-or-nothing from the Apps Script's point of view.**
  The Gmail thread is only labeled (and thus considered "processed")
  once the backend confirms the record was fully persisted (a real HTTP
  200, which requires both the Supabase insert and the Sheets push to
  have succeeded). Any failure leaves the thread unlabeled, so it's
  automatically retried on the next run — safely, thanks to the dedup
  behavior above.
- **The destination mailbox also receives unrelated mail** (not just
  forwarded office correspondence), so the Apps Script only ever
  processes messages carrying a specific label. In production, a Gmail
  filter applies that label automatically based on the known forwarding
  sender's address — no manual labeling is needed for normal operation.
- **Google credentials stay inside Apps Script, not the backend.** The
  backend never talks to Gmail, Sheets, or Drive APIs directly — it only
  calls Claude and Supabase, and pushes to a webhook URL. All Google-side
  access (reading Gmail, applying labels, the Sheets webhook itself)
  is handled by Apps Script running under an already-authorized Google
  account. This avoids adding any new Google service-account or OAuth
  credentials to the backend.

## Components

| Component | Location | Role |
|---|---|---|
| Email ingest endpoint | `backend/app/routes/email.py` | Orchestrates dedup check, Claude extraction, Supabase insert, Sheets push |
| Request/response schema | `backend/app/schemas/email.py` | `EmailIngestRequest`/`EmailIngestResponse` |
| Supabase persistence | `backend/app/services/supabase_service.py` | `insert_data()` (extended with optional `message_id` and `attachments_link`), `find_submission_by_message_id()` |
| LLM extraction (reused) | `backend/app/services/claude_service.py` | Shared with the OCR scanning flow; uses Claude and falls back to Gemini when Claude's API is unavailable |
| Sheets webhook push (reused) | `backend/app/services/sheets_service.py` | Unmodified — shared with the OCR scanning flow |
| Gmail poller | `docs/apps-script/gmail-grievance-classifier.gs` | Also uploads attachments to Drive. Not deployed via this repo (Apps Script has no native git integration) — kept here as a version-tracked reference copy; the live version lives in a Google Apps Script project |
| Existing Sheets sync (reference only) | `docs/apps-script/sync-grievances.gs` | Copy of the live script bound to the DAAK Records spreadsheet (it also holds only this sync; the webhook that writes rows lives in a different project). Must stay in its own project — pasting another script over it removes `syncGrievances()` |

## Data model

Supabase submissions table gains additive, backward-compatible columns
beyond what the OCR flow already used:

- `message_id` (nullable, unique) — the Gmail message ID; `NULL` for
  scanned-document rows, set for email-sourced rows. Used purely for
  deduplication.
- `attachments_link` (nullable text) — link to the email's Drive folder;
  `NULL` when the email has no attachments and for scanned documents.
  Migration: `ALTER TABLE document_submission ADD COLUMN attachments_link text;`

The Sheets payload is unchanged in shape from the scanned-document
flow — same field set, just sourced from an email's text instead of OCR
output. The attachments link deliberately does **not** add a Sheet
column: it is sent as the existing `filename` value (see Email
attachments below).

## Constraints and external dependencies

- **The script that actually writes rows to DAAK Records upon receiving
  the Sheets webhook is external to this repo and its implementation is
  unknown** — it's a separate deployment from the Grievances-sync script
  referenced above. Any change requiring a new column in DAAK Records
  needs testing against that unknown script first, which is why the
  attachments link reuses an existing column (see Email attachments).
- **The destination Gmail account is a standard (non-Workspace) personal
  account.** This limits what's possible for anything involving Drive
  sharing (see Email attachments) to public "anyone with the link"
  access, or to a folder shared manually with named staff accounts —
  there's no domain-restricted sharing option available.
- **This is a two-repo setup**: a dev/testing repository and a
  production-counterpart repository, tracked as separate git remotes.
  This feature has so far only existed on a feature branch of the
  production-counterpart repository, not yet merged into its main
  branch.

## Current state

- The email classification pipeline is implemented and has been
  exercised successfully against real forwarded grievance emails,
  including through multi-hop forwarding chains (the extraction
  correctly identifies the original citizen complainant rather than
  whoever relayed the email).
- The feature branch is pushed to its remote but not merged. `main` is
  untouched.
- The production backend deployment is currently unavailable due to an
  exhausted hosting usage limit. Development and testing are proceeding
  against a locally-run backend (via Docker) exposed to the internet
  through a temporary tunnel, since the Gmail Apps Script needs a public
  URL to call. This is inherently fragile — the local backend and tunnel
  go down whenever the host machine sleeps or restarts, and must be
  manually restarted (`docker compose up -d` in `backend/`, then restart
  the tunnel process) before Gmail processing will succeed again.
- If Claude's API is unavailable (for example exhausted credits),
  classification falls back to Gemini. If both fail, the failure is
  safe: it happens before any data is written, and the Gmail poller's
  retry-safe design means the email is automatically reprocessed
  later, without creating duplicates.
- Email attachment support (Drive upload + link on the record and Sheet)
  is implemented and unit-tested but **not yet rolled out** — see Email
  attachments below for the remaining manual steps.
- An automatic polling trigger (checks for new labeled mail on a fixed
  interval) has been installed on the Gmail Apps Script project, so
  processing resumes on its own once the local backend/tunnel and
  Anthropic credits are both available again — no manual re-triggering
  needed at that point.

## Known implementation details worth preserving

- One of the backend service files used by the (separate) OCR scanning
  flow loads its local environment file from an unexpected relative
  path, inconsistent with the rest of the app. This is pre-existing and
  unrelated to the email feature, but it means local (non-Docker)
  testing of the full app requires an environment file in two locations
  to work around it. Running via Docker Compose sidesteps this
  entirely, since Docker injects environment variables directly rather
  than relying on that file-loading call — this is why local development
  for this feature standardized on Docker Compose rather than running
  the backend directly.
- Claude can legitimately return a null category when nothing in the
  fixed category list fits (e.g. a clearly non-grievance, non-official
  email). The response schema requires a non-null category string, so
  this must be normalized (e.g. to a placeholder value) alongside the
  other optional fields before constructing the response — omitting
  this normalization causes a response validation error *after* the
  record has already been successfully persisted, which is a
  particularly confusing failure mode to debug since the caller sees an
  error despite the data having been saved correctly.
- The Gmail poller's search must be scoped by label rather than
  scanning the whole inbox, precisely because the destination mailbox
  receives unrelated mail. An unscoped search would classify and
  formally record unrelated personal or promotional email as if it were
  official correspondence.

## Email attachments (implemented, awaiting rollout)

Grievance emails often carry photos, PDFs or videos. Staff working the
Grievances sheet can now open them from the record.

**How it works**
- The Gmail Apps Script uploads the email's attachments to one Google
  Drive folder per email (folder named after the Gmail message ID, files
  numbered `01_name`, `02_name`, ... so same-named files never collide)
  and sends the folder link to the backend as `attachments_link`. Apps
  Script is used because it already holds the email and runs as the
  mailbox's own Google account — the backend needs no Google credentials,
  no token files, no second Gmail read, and no new dependencies.
- The backend validates the link (Drive URLs only), stores it on the
  Supabase record, and sends it to the Sheet as the existing `filename`
  value. This reuses the `Filename` column that the Sheets script and the
  Grievances sync already carry end to end, so no column is added and the
  Sheet layout (including the manually used `STATUS` column) is
  untouched. It is a plain URL on purpose: the Grievances sync copies
  with `getValues()`, which flattens formulas and rich-text links.
  Emails without attachments keep the previous `gmail:<message_id>` value
  and send exactly the same request as before.
- Failure handling: Drive work happens before the backend call. If Drive
  fails, nothing is recorded or labeled and the next run retries,
  reusing the same folder (no duplicates). The Sheet is append-only, so
  holding the email back is preferred to saving it without its files.
  A script lock prevents overlapping runs; a time budget stops a run
  before Apps Script's 6-minute limit.
- Scope decisions: email attachments only (the OCR scanning flow keeps
  not retaining original images); all attachment types; one folder link
  per email; only the last message in a thread is processed (existing
  behaviour). Inline images are kept only when large (default 50 KB) so
  signature logos are skipped but photos pasted into the body are not;
  set `INLINE_IMAGE_MIN_BYTES` to -1 to skip all inline images.
- Sharing: by default each folder is "anyone with the link can view" (the
  only option on a personal Gmail account), so anyone who obtains a link
  can open the files. A safer alternative when all staff have Google
  accounts: create a folder, share it with them, put its ID in
  `DRIVE_PARENT_FOLDER_ID`, and set `SHARE_ANYONE_WITH_LINK` to `false`
  (new folders inherit the parent's sharing).

**Rollout steps (in this order)**
1. Run the Supabase migration above (an email with attachments would
   fail to insert without the column).
2. Restart the backend so it loads the new code (the container
   bind-mounts the code; no image rebuild is needed).
3. Paste the updated Apps Script into the live project, then run
   `processInbox` once by hand and approve the new Drive permission —
   otherwise the already-installed trigger fails authorization.
4. Test with clearly marked test emails behind the input label: no
   attachment; one photo; two same-named files; a PDF; a small video;
   re-run the same email (no second folder or row); check the cell in
   DAAK Records and in Grievances Data after a sync, and that the
   `STATUS` column is unchanged. Clean up test rows and folders.

**Assumptions to verify on the first real test**
- The external Sheets-writing script puts `filename` into the `Filename`
  column as plain text, as it does for scanned documents.
- The URL is clickable in DAAK Records and in Grievances Data after a
  sync.
- Staff can open the folders (see Sharing).
- A manual "Forward" keeps the original attachments as normal
  attachments.

**Known limitations**
- Emails processed before this feature have no link, and the append-only
  Sheet cannot be updated afterwards.
- Drive storage on a personal account is 15 GB shared with that
  account's Gmail and Photos; videos can fill it (the run log reports
  usage).
- OCR of attached scanned letters through the existing OCR flow is not
  done; it would need the file bytes on the backend.

## Local development setup (no secrets included)

Running this feature locally requires:
- A backend environment file with real credentials for Claude, Supabase,
  and the Sheets webhook, plus a shared secret for authenticating the
  Gmail poller's calls to the backend — kept out of version control.
- The backend run via Docker Compose (`docker compose up -d` from
  `backend/`) rather than directly, for the reasons noted above.
- A public tunnel to the locally-running backend, since Apps Script
  needs a real URL to call — currently a temporary tunnel is used as a
  stand-in for the production deployment.
- An Apps Script project (separate from the existing Grievances-sync
  script) authorized against the destination Gmail account, configured
  with the backend's public URL and shared secret.
