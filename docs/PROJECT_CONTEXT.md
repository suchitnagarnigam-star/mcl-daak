# MCL Patr — Project Context Handoff

**Last updated:** August 19, 2026

## Purpose

MCL Patr is a municipal document digitization system for Municipal Corporation Ludhiana. It extracts structured data from multilingual correspondence, stores the result in Supabase, and syncs it to Google Sheets.

Yuvraj prefers direct explanations of what changed and why, minimal unsolicited recommendations, and no unnecessary hedging.

## Repository / git workflow

- Repository: `yuvrajsingh0125/MCL-OCR`
- Remote `origin`: dev/testing repo
- Remote `daak`: production counterpart at `suchitnagarnigam-star/mcl-daak`
- Current local branch: `uv-dev`
- `uv-dev` is the active branch for backend, LLM, routing, UI, and persistence changes
- `frontend` remains the branch for OpenCV preprocessing and camera-focused frontend work
- `daak/main` and `daak/duv-dev` are aligned to the current `uv-dev` commit

## Live deployments

- Frontend dev: `https://mcl-ocr.vercel.app`
- Backend dev: `https://mcl-ocr.onrender.com`
- Frontend prod: `https://mcl-daak.vercel.app`
- Backend prod: `https://mcl-daak.onrender.com`

## Current architecture

```text
React 19 + Vite + TypeScript
        ↓
FastAPI
        ↓
Temporary save to uploads/
        ↓
OpenCV preprocessing
        ↓
Mistral OCR (primary)
        ↓
Delete temp files from disk
        ↓
Claude extraction on combined OCR text
        ↓
Supabase serial number generation + storage
        ↓
Google Sheets webhook sync
        ↓
Return JSON response
```

**The system is stateless on disk after each request.** No output JSON is written and no uploaded images persist beyond OCR. Supabase is the source of truth.

## Important OCR status

The current plan uses **Mistral OCR as the primary OCR engine**. PaddleOCR is no longer part of the deployment target. Any stale doc describing PaddleOCR as an active fallback should be treated as outdated.

## Current repository structure

```text
backend/app/
  main.py
  config.py
  routes/
    upload.py
    history.py
    health.py
  services/
    mistral_ocr_services.py
    claude_service.py
    opencv_services.py
    sheets_service.py
    supabase_service.py
    gemini_service.py
  utils/
    file_utils.py
  schemas/

frontend/src/
  App.tsx
  index.css
  main.tsx
  components/
    TopNav.tsx
    DockNavigation.tsx
  screens/
    CameraScreen.tsx
    ProcessingScreen.tsx
    ResultScreen.tsx
    HistoryScreen.tsx
```

## Extracted fields

Claude now targets 9 fields. `subject` and `summary` are required gate fields.

```json
{
  "date": "",
  "subject": "",
  "summary": "",
  "department": "",
  "category": "",
  "sender_name": "",
  "sender_contact": null,
  "receiver": "",
  "reference_number": null
}
```

- `department` is matched against a hardcoded list of 22 MCL departments
- `category` is matched against a hardcoded list of 10 categories
- `category` must be preserved through history and result rendering

## Multi-image upload

The `/upload/` endpoint accepts 1 to N images as one submission.

Pipeline per request:

1. Generate `submission_id` with `uuid4()` on request receipt.
2. For each image, save temporarily, preprocess, run Mistral OCR, then delete both temp files.
3. Keep only `{ img_index, filename, ocr_md }` in memory.
4. Concatenate all OCR with page markers so Claude sees the document as a whole.
5. Call Claude once.
6. Insert the result into Supabase, which generates the serial number.
7. Push the result to Google Sheets.
8. Return the response without writing any result file.

### API contract

```text
POST /upload/
Body: multipart/form-data with files=[...]

Success response:
{
  serial_number,
  message,
  submission_id,
  status: "complete",
  file_count,
  files,
  images,
  extracted_data
}
```

### Multi-image failure behavior

The current endpoint still fails the whole submission if one image fails OCR. That behavior is unresolved and should be decided explicitly before expanding the multi-image flow further.

## Storage

- Supabase/PostgreSQL is the only operational data store.
- `insert_data()` in `supabase_service.py` generates `serial_number` values in the form `MCL/{year}/{number}`.
- The backing table is `document_submission`.
- Status values are `pending`, `complete`, and `failed`.
- Google Sheets receives the final structured payload through webhook sync.
- The `output/` directory is obsolete, and `save_result_json()` is dead code.

## Frontend / camera

The frontend is structured around a global app shell with the camera, processing, result, and history screens under `frontend/src/screens/`.

Target UX:

```text
Capture / upload
      ↓
Preview
      ↓
Processing status
      ↓
OCR + Claude
      ↓
Structured result
      ↓
Review/edit
      ↓
Save
```

The application is expected to work on both mobile and web.

## Deployment / security

- Docker is the runtime for the backend.
- HTTPS deployment is needed for camera access in browsers.
- No authentication or RBAC is implemented.
- No agents, no streaming, and no permanent image storage.

## Current technical debt

- Stale import in `config.py` line 1: `from anthropic.types import completion_create_params`
- `save_result_json()` still exists in `file_utils.py` but is unused
- Department and category lists are hardcoded in `claude_service.py`
- The service stack is synchronous and blocks the event loop
- No file type or size validation is present
- Multi-image OCR failure still aborts the entire submission

## Immediate roadmap

1. Remove dead code and stale imports.
2. Decide how partial multi-image OCR failures should behave.
3. Add input validation for upload size and type.
4. Add Pydantic schemas under `schemas/`.
5. Keep the docs aligned with the current branch and remote layout.
