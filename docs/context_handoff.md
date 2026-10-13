# MCL Patr — Project Context

## What this is
MCL Patr is a document digitization system for Municipal Corporation
Ludhiana (MCL). Correspondence arrives in English, Hindi and Punjabi on
two channels, and both end up as the same kind of record:

1. **Paper**: staff photograph or upload documents in the web app
   (OCR → extraction).
2. **Email**: office correspondence is forwarded to a dedicated Gmail
   inbox and picked up automatically (extraction → record), including
   any attachments.

Every item gets a serial number, is stored in Supabase, and is appended to
a Google Sheet ("DAAK Records"). Grievance-category items are additionally
mirrored into a separate "Grievances Data" sheet that staff work from.

## Repository, branches and deployment
- One remote, `origin` → `github.com/suchitnagarnigam-star/mcl-daak`.
  `main` is production.
- Other branches on `origin` that are **not** merged:
  - `uv-dev` — one commit: upload hardening and an extraction prompt that
    resists prompt injection. Still worth adopting (see Follow-ups).
  - `aman-dev` — an abandoned alternative implementation of email
    attachments by a former contributor. It makes the backend read Gmail
    itself through OAuth and runs a sync at startup. It is intentionally
    not merged: it duplicates the Apps Script ingestion, can pull the
    whole mailbox history at startup (no date limit when its state table
    is empty), needs OAuth token files on the host, silently drops
    attachments on any Gmail error, and creates duplicate Drive folders
    on retry. Do not merge it as is.
  - `copilot/uv-dev` — old, unused.
- Backend runs on Render (service `mcl-daak`, Pro plan, Docker build from
  `backend/`): `https://mcl-daak.onrender.com`. Frontend runs on Vercel:
  `https://mcl-daak.vercel.app`. Environment values live in the Render and
  Vercel dashboards, never in the repo. Confirm in the Render dashboard
  which branch auto-deploys.
- Older dev deployments (`mcl-ocr.*`) come from an earlier dev repository
  and are not maintained.

## Pipelines

### Scanned documents (`POST /upload/`)
```text
React app (camera capture / file upload)
  → FastAPI POST /upload/
  → save upload temporarily → OpenCV preprocessing → Mistral OCR per page
  → delete temp files immediately (nothing is kept on disk)
  → combine page text → LLM extraction (Claude, Gemini fallback)
  → reject empty OCR / missing subject or summary
  → Supabase insert (serial number, status "pending")
  → Google Sheets webhook → Supabase status "complete"
```

### Email (`POST /classify-email/`)
```text
Office inbox forwards correspondence to the dedicated Gmail inbox
  → a Gmail filter labels mail from the known sender (MCL-Grievance-Input)
  → Gmail Apps Script (every 30 min) finds labeled, unprocessed threads
      → uploads attachments to one Drive folder per email (if any)
      → POSTs the email to the backend
  → Backend:
      1. dedup by Gmail message_id (already recorded → return stored result)
      2. same LLM extraction as above, on "From/Subject/Date + body"
      3. Supabase insert (same serial numbers) → Sheets webhook → "complete"
  → Apps Script labels the thread (Grievance / Non-Grievance +
    AutoClassified) only if the backend answered 200
  → syncGrievances() copies grievance rows into Grievances Data
```

## Backend structure
```text
backend/app/
  main.py            # FastAPI init, CORS, router registration, keep-alive ping
  config.py          # env loading; Anthropic, Gemini and Supabase clients
  routes/
    upload.py        # POST /upload/
    history.py       # GET /history/
    email.py         # POST /classify-email/
    health.py        # GET / and /health
  schemas/
    email.py         # EmailIngestRequest / EmailIngestResponse
    request.py, response.py   # empty placeholders
  services/
    mistral_ocr_services.py   # OCR
    opencv_services.py        # image preprocessing
    claude_service.py         # extraction prompt, Claude call, Gemini fallback
    supabase_service.py       # serial numbers, inserts, lookups, status
    sheets_service.py         # Sheets webhook push
  utils/file_utils.py         # temp-file helpers (save_result_json is dead code)
backend/tests/                # see Follow-ups for which tests run
docs/apps-script/             # reference copies of the two Apps Scripts
```
Frontend (React 19 + Vite + TypeScript): `App.tsx` (shell and routing),
screens `CameraScreen`, `ProcessingScreen`, `ResultScreen`, `HistoryScreen`,
components `TopNav`, `DockNavigation`.

## Extraction
`process_document()` in `claude_service.py` is shared by both channels. It
calls Claude and, if Claude's API is unavailable (for example exhausted
credits), falls back to Gemini (`GEMINI_FALLBACK_MODEL`). The fallback has
not yet been exercised in production and its model name has not been
validated there. If both fail the request errors before anything is saved.

It returns 9 fields; `subject` and `summary` are required (missing → the
request is rejected):
`date, subject, summary, department, category, sender_name,
sender_contact, receiver, reference_number`.

- `department` is chosen from 22 hardcoded MCL departments.
- `category` is chosen from 15 hardcoded categories: Public Grievance,
  Development & Ward Work, RTI Application, Legal & Court Correspondence,
  Inter-Department Reference, Building Plan & Construction, Property Tax,
  VIP & Political Reference, Trade & Fire License, Vigilance & Misconduct,
  Tender & Contractor, HR & Service Matter, Audit Para, Council Matter,
  General Correspondence.
- The model may legitimately return `null` for `category`/`department`
  when nothing fits. The scan flow stores that as given; the email route
  normalizes empty fields to `N/A` (the response model requires a
  non-null category, otherwise it fails *after* the record was saved).

## Storage
- Serial number: `MCL/{year}/{n}`, starting at 1001 each year; generated in
  `supabase_service.insert_data()` (max + 1, not strictly atomic).
- Supabase table `document_submission`: the 9 fields plus `serial_number`,
  `status` (`pending` | `complete` | `failed`), `created_at`, and two
  columns used only by the email channel (NULL for scans):
  - `message_id` — unique; the Gmail message ID, used for deduplication.
  - `attachments_link` — link to the email's Drive folder.
  Migrations are manual (Supabase SQL editor):
  `ADD COLUMN message_id text UNIQUE;`
  `ADD COLUMN attachments_link text;`

## API contracts

### `POST /upload/`
Multipart field `files`. Success returns `serial_number`, `submission_id`,
`status: "complete"`, `file_count`, `files`, `images` (`img_index`,
`filename`, `ocr_md`) and `extracted_data`. Gate failures return 400/422
with `status: "failed"`.

### `GET /history/`
Newest 10 submissions from Supabase (`id`, `serial_number`, `created_at`,
`llm_result`).

### `POST /classify-email/`
Header `X-Email-Webhook-Secret` must equal `EMAIL_WEBHOOK_SECRET` (else 401).
Body: `message_id`, `thread_id`, `sender`, `subject`, `body`, `received_at`,
optional `attachments_link` (accepted only if it starts with
`https://drive.google.com/`; otherwise ignored with a warning).
Response: `category`, `is_grievance`, `serial_number`, `summary`,
`department`. Errors: 401 bad secret, 422 missing subject/summary, 502 LLM
error, 500 database/Sheets failure. It is **idempotent per `message_id`**:
a completed message returns its stored result; a message left "pending"
by a partial failure is retried only for the failed step. Nothing is marked
complete unless the Sheets write succeeded, so callers can safely retry.

## Environment variables (backend)
```text
MISTRAL_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY (fallback; optional)
SUPABASE_URL, SUPABASE_KEY
SHEETS_WEBHOOK_URL, SHEETS_SECRET
EMAIL_WEBHOOK_SECRET   # must equal CONFIG.BACKEND_SECRET in the Gmail script
KEEP_ALIVE_URL, CORS_ORIGINS
```
`.env.example` lists the names. Frontend: `VITE_API_URL`.
`GOOGLE_SHEET_ID` / `GOOGLE_DRIVE_FOLDER_ID` are declared but unused.

## Google Sheets and Apps Script
Three separate Apps Script projects are involved. **Each lives in its own
project; never paste one over another** (that deletes the other's code).

1. **Sheets-writing web app** (behind `SHEETS_WEBHOOK_URL`). Receives each
   record from the backend and appends a row to **DAAK Records** (a
   spreadsheet with automatic monthly tabs). **Not in this repo; its
   source has not been documented.** Known behaviour: rows are append-only
   (a row cannot be updated afterwards); the payload key `FILE_LOCATION`
   fills the **Attachment Folder** column; `filename` fills **Filename**.
2. **`syncGrievances()`** — bound to the DAAK Records spreadsheet (reference
   copy: `docs/apps-script/sync-grievances.gs`). Rebuilds the first tab of
   the separate **Grievances Data** spreadsheet from DAAK Records:
   - keeps rows whose category contains "grievance" (not "non-grievance");
     so only categories with that word reach Grievances Data — a genuine
     complaint filed under e.g. "Building Plan & Construction" does not;
   - copies columns by **position**, then restores each row's `STATUS` by
     Serial Number, so staff-entered statuses survive. `STATUS` must stay to
     the right of every DAAK Records column; a new DAAK Records column that
     lands on it overwrites it. Any other column staff type into on
     Grievances Data is cleared by each run;
   - nothing else should write to Grievances Data.
3. **Gmail classifier** — standalone project (reference copy:
   `docs/apps-script/gmail-grievance-classifier.gs`), authorised as the
   dedicated Gmail account, with a 30-minute time trigger. Details below.

## Email channel details

### Key decisions
- **Reuse the document pipeline** rather than build a parallel one: same
  extraction, serial numbers and Sheets webhook, so email and scanned
  records have the same shape.
- **Every email gets a record**, grievance or not, like every scanned
  document. Only grievance-category rows reach Grievances Data.
- **Google access stays in Apps Script.** The backend never calls Gmail,
  Drive or Sheets APIs, so it needs no Google credentials or token files.
- **All-or-nothing labeling.** A thread is labeled processed only after
  the backend answers 200; any failure leaves it unlabeled and the next
  run retries it safely (deduplication prevents duplicates).
- **Label gate.** The inbox also receives unrelated mail, so only messages
  carrying `INPUT_LABEL` are touched (a Gmail filter applies it to mail
  from the forwarding sender). `PROCESS_AFTER` is a hard date floor so old
  mail is never picked up. Never scan the whole inbox.
- Only the **last message of a thread** is processed.

### Attachments
- The Gmail script uploads an email's attachments to one Drive folder per
  email (named after the message ID, files numbered `01_name`, `02_name`…
  so same-named files don't collide) under a root folder
  "MCL Grievance Attachments" (reused if one already exists), then sends the
  folder link as `attachments_link`.
- The backend stores the link in Supabase and sends it to the Sheet as
  `FILE_LOCATION` (→ Attachment Folder). It is a plain URL on purpose: the
  sync copies values, which would flatten a formula or rich-text link.
  Emails without attachments send no link and leave that cell empty. The
  Sheet's Filename for email rows is the fixed text `Email`.
- Drive work happens **before** the backend call. If Drive fails, nothing is
  recorded or labeled and the email is retried (the Sheet is append-only,
  so a record without its files could never be fixed later). Folders and
  files are reused on retry; a script lock prevents overlapping runs; a
  time budget keeps a run under Apps Script's 6-minute limit.
- Inline images are kept only above `INLINE_IMAGE_MIN_BYTES` (default 50 KB)
  so signature logos are skipped but photos pasted into the body are not;
  set it to -1 to skip all inline images.
- Sharing: by default each folder is "anyone with the link can view" (the
  only option on a personal, non-Workspace Gmail account), so anyone with a
  link can open the files. Safer: create a folder, share it with the staff
  accounts, set `DRIVE_PARENT_FOLDER_ID` to it and
  `SHARE_ANYONE_WITH_LINK` to `false`.

### Gmail script configuration (`CONFIG` at the top of the script)
`ENV` (`'test'` or `'prod'`) selects `ENVIRONMENTS[ENV].BACKEND_URL`;
`BACKEND_SECRET` (must equal `EMAIL_WEBHOOK_SECRET`); `INPUT_LABEL`;
`LABEL_GRIEVANCE` / `LABEL_OTHER` / `LABEL_PROCESSED`; `PROCESS_AFTER`;
`BATCH_SIZE`; `RUN_TIME_BUDGET_MS`; `TRIGGER_INTERVAL_MINUTES`; the Drive
settings above. The repo copy contains placeholders — after pasting it into
the live project, re-enter the real URL and secret.

### Operating it
- After changing the script, run `processInbox` once by hand and approve
  any new permission, otherwise the installed trigger fails authorization.
  Install the trigger once with `installTrigger()`; remove with
  `removeTrigger()`.
- Health check: Apps Script *Executions* should show a time-driven run
  about every 30 minutes; threads that stay unlabeled have failed or are
  waiting for the next run.
- Failure modes (all safe, nothing lost): backend down → threads wait; Claude
  unavailable → Gemini fallback; both unavailable → threads wait; Drive
  failure → threads wait.
- To test without touching real mail, run a backend locally
  (`docker compose up -d` in `backend/`, exposed through a tunnel) and set
  `ENVIRONMENTS.test.BACKEND_URL` to it; use clearly marked test emails
  (subject starting `TEST - DO NOT ACTION`), apply the input label by hand,
  and delete the test rows (Supabase and DAAK Records) and Drive folders
  afterwards. Supabase and the Sheets are shared with production, so test
  rows are real rows until deleted.
- Two environment-file quirks matter only for non-Docker local runs: the
  OCR service reads its key at import time and loads `.env` from
  `backend/app/` instead of `backend/`. Docker and Render inject variables
  directly, so they are unaffected.

## Follow-ups and technical debt
- **Prompt injection:** email text is untrusted input to the extraction
  prompt. Adopt the hardened prompt from `uv-dev` (keep it inside
  `_build_prompt` in `claude_service.py`).
- **Drive:** decide on sharing (above); delete folders created for emails
  that were already recorded before attachment support (anything under the
  root folder not linked from a record); watch storage (15 GB on a personal
  account, shared with its Gmail/Photos).
- **Supabase:** tables `email_sync_state` and `processed_gmail_messages`
  were created by the abandoned branch and are unused.
- **Tests:** `pytest tests/test_history_route.py tests/test_email_attachments.py`
  runs. `test_gemini_service.py` (imports a module that does not exist) and
  `test_mistral_service.py` (needs a local image, calls a real API at import)
  fail at collection and should be fixed or removed.
- `main.py` pings `KEEP_ALIVE_URL` every 10 minutes (only needed on
  Render plans that sleep); `save_result_json()` is dead code; the
  department/category lists are hardcoded; services are synchronous;
  uploads have no type/size validation; a failed page fails the whole
  multi-image submission; `schemas/request.py` and `response.py` are empty.
- If a shared secret is ever pasted into chat or logs, rotate it
  (backend env var and the Apps Script `BACKEND_SECRET` together).
- Emails recorded before attachment support have no link, and the
  append-only Sheet cannot be updated afterwards.

## Priority order
1. Finish the production cutover and watch it (Executions, Render logs,
   new rows, Drive links, STATUS surviving a sync).
2. Prompt-injection hardening.
3. Fix or remove the broken tests; clean up dead code.
4. Async refactor of network/CPU-bound calls.
5. Upload validation and better multi-image failure handling.
