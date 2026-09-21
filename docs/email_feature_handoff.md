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
  script that populates it does a full clear-and-rewrite of that sheet
  on every run, sourced only from DAAK Records. Anything written to the
  Grievances sheet directly would be wiped on the next sync. That sync
  script also only recognizes a category as a grievance by a substring
  match on the word "grievance" — categories that are clearly complaints
  in plain English but don't contain that word (e.g. a construction/
  encroachment complaint) will not appear there, even though they're
  correctly recorded in DAAK Records.
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
| Supabase persistence | `backend/app/services/supabase_service.py` | `insert_data()` (extended with an optional `message_id`), `find_submission_by_message_id()` |
| Claude extraction (reused) | `backend/app/services/claude_service.py` | Unmodified — shared with the OCR scanning flow |
| Sheets webhook push (reused) | `backend/app/services/sheets_service.py` | Unmodified — shared with the OCR scanning flow |
| Gmail poller | `docs/apps-script/gmail-grievance-classifier.gs` | Not deployed via this repo (Apps Script has no native git integration) — kept here as a version-tracked reference copy; the live version lives in a Google Apps Script project |
| Existing Sheets sync (reference only) | `docs/apps-script/sync-grievances.gs` | Verbatim copy of a pre-existing, independently-deployed script for compatibility reference — not modified or owned by this feature |

## Data model

Supabase submissions table gains one additive, backward-compatible
column beyond what the OCR flow already used:

- `message_id` (nullable, unique) — the Gmail message ID; `NULL` for
  scanned-document rows, set for email-sourced rows. Used purely for
  deduplication.

No other schema changes. The Sheets payload is unchanged in shape from
the scanned-document flow — it's the same field set, just sourced from
an email's text instead of OCR output.

## Constraints and external dependencies

- **The script that actually writes rows to DAAK Records upon receiving
  the Sheets webhook is external to this repo and its implementation is
  unknown** — it's a separate deployment from the Grievances-sync script
  referenced above. Any change requiring a new column in DAAK Records
  needs testing against that unknown script first (see Planned next
  work).
- **The destination Gmail account is a standard (non-Workspace) personal
  account.** This limits what's possible for anything involving Drive
  sharing (see Planned next work) to public "anyone with the link"
  access — there's no domain-restricted sharing option available.
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
- The Anthropic API key currently in use has an exhausted credit
  balance, so classification calls fail until credits are added. This
  failure mode is safe: failures happen before any data is written, and
  the Gmail poller's retry-safe design means affected emails are
  automatically reprocessed once credits are restored, without creating
  duplicates.
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

## Planned next work (not started)

**Attachments.** Grievance emails often include photos, PDFs, or videos
that staff working the Grievances sheet currently have no way to access
without going back to the original email. The intended design:

- The Gmail poller uploads an email's real (non-inline) attachments to a
  dedicated Google Drive folder — one folder per email — using Apps
  Script's built-in Drive access (no new credentials needed), shared as
  "anyone with the link" (the only sharing option available given the
  non-Workspace account constraint noted above).
- The resulting folder link is threaded through the backend the same
  way other optional fields are: added to the request schema, included
  in the record sent to Supabase (as a new nullable, additive column)
  and to the Sheets payload.
- **Open question requiring investigation before implementation**:
  whether the external DAAK-Records-writing script (see Constraints)
  automatically accommodates a new field as a new column, or silently
  drops unrecognized fields. This should be tested empirically (sending
  a synthetic payload with a new field and observing whether a column
  appears, checked across more than one of DAAK Records' tabs) before
  committing to that approach. If new fields are dropped, the fallback
  is to append the attachment link as a clearly delimited line within
  the existing summary field, which is already guaranteed to reach both
  DAAK Records and the Grievances sheet.
- Confirmed scope: email attachments only (the OCR scanning flow is
  intentionally out of scope and keeps its current behavior of not
  retaining original images); all attachment types; one folder link per
  email rather than one link per attachment; inline/embedded images
  (e.g. signature logos) excluded.
- Operational considerations to keep in mind: Drive storage is limited
  on a standard personal account and shared with that account's other
  usage, so attachment volume (especially video) should be monitored;
  and "anyone with the link" sharing means attachment contents are
  accessible to anyone who obtains a link, which is an inherent
  limitation of the non-Workspace account rather than something the
  implementation can avoid.

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
