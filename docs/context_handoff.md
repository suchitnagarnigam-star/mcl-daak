# MCL Patr — Context Handoff (August 19, 2026)

## What this is
MCL Patr is a municipal document digitization system for Municipal Corporation Ludhiana. It extracts structured data from multilingual correspondence in English, Hindi, and Punjabi/Gurmukhi, then stores the result in Supabase and syncs it to Google Sheets.

Yuvraj prefers direct, first-principles explanations, minimal hedging, and learning-by-doing. If the tone shifts to more directive output under deadline pressure, follow that shift.

## Repository state
- `origin` → https://github.com/yuvrajsingh0125/MCL-OCR.git (dev/testing repository)
- `daak` → https://github.com/suchitnagarnigam-star/mcl-daak.git (production counterpart)
- Current local branch: `uv-dev`
- `uv-dev` is the active working branch for backend, LLM, routing, UI, and persistence changes
- `frontend` is still the branch for OpenCV preprocessing and camera-heavy frontend work
- `daak/duv-dev` and `daak/main` are currently aligned to the current `uv-dev` commit
- `origin` and `daak` should be treated as separate remotes with separate deployment targets

## Current deployment map
- Dev frontend: https://mcl-ocr.vercel.app
- Dev backend: https://mcl-ocr.onrender.com
- Prod frontend: https://mcl-daak.vercel.app
- Prod backend: https://mcl-daak.onrender.com
- `.env.production` is not committed; environment values live in Vercel/Render dashboards

## Current pipeline
```text
React 19 + Vite + TypeScript
    ↓
FastAPI POST /upload/ and GET /history/
    ↓
Save upload temporarily to uploads/
    ↓
OpenCV preprocessing → processed/
    ↓
Mistral OCR per image
    ↓
Delete temp files from disk immediately
    ↓
Combine OCR text in memory with page markers
    ↓
Claude single pass on combined document text
    ↓
Reject empty OCR, empty LLM output, or missing subject/summary
    ↓
Supabase insert → serial number + pending status
    ↓
Google Sheets webhook sync
    ↓
Supabase status update to complete
    ↓
Return JSON response
```

**The system is stateless on disk after each request.** No result JSON is written. No uploaded images persist after OCR. Supabase is the source of truth for stored records.

## Current backend shape
```text
backend/app/
  main.py                       # FastAPI init, CORS, router registration, keep-alive
  config.py                     # Anthropic, Mistral, Supabase client setup
  routes/
    upload.py                   # POST /upload/ orchestration and gates
    history.py                  # GET /history/ from Supabase
    health.py
  services/
    mistral_ocr_services.py     # OCR API integration
    claude_service.py           # 9-field extraction incl. category
    opencv_services.py          # image preprocessing before OCR
    supabase_service.py         # serial numbers, insert, history fetch, status updates
    sheets_service.py           # Google Sheets webhook push
    gemini_service.py           # available but not on the main path
  utils/
    file_utils.py               # save/delete helpers; save_result_json() is dead
  schemas/
    # still empty
```

## Current frontend shape
```text
frontend/src/
  App.tsx                       # global shell and route state
  index.css                     # design tokens and global styles
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
Claude now extracts 9 fields. `subject` and `summary` are required gate fields; if either is missing, the pipeline fails.

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

- `department` is matched against a hardcoded list of 22 departments in `claude_service.py`
- `category` is matched against a hardcoded list of 10 categories in `claude_service.py`
- `category` must flow through `history.py`, `ResultScreen`, and Supabase storage

## Categories
1. Grievance
2. Service Request
3. Development & Infrastructure
4. Financial & Budgetary
5. Legal & Compliance
6. Administrative & HR
7. Licensing & Permits
8. Public Health & Sanitation
9. Property & Estate
10. General Correspondence

## Serial numbers and storage
- Serial number format: `MCL/{year}/{sequential_number}`
- Serial numbers start at 1001 if no records exist for the current year
- `supabase_service.insert_data()` generates the serial number and inserts the row
- The target table is `document_submission`
- Status values are `pending`, `complete`, and `failed`

## API contracts

### POST /upload/
- Multipart field: `files`
- Success response includes `serial_number`, `submission_id`, `status: "complete"`, `file_count`, `files`, `images`, and `extracted_data`
- `images[]` only contains `img_index`, `filename`, and `ocr_md`
- Gate failures return 400/422 with `status: "failed"`

### GET /history/
- Returns the newest 10 submissions from Supabase
- Each item includes `id`, `serial_number`, `created_at`, `llm_result`, and placeholder OCR text
- Source is Supabase only

## Environment variables

### Backend
```text
MISTRAL_API_KEY=
ANTHROPIC_API_KEY=
SUPABASE_URL=
SUPABASE_KEY=
SHEETS_WEBHOOK_URL=
SHEETS_SECRET=
KEEP_ALIVE_URL=https://mcl-ocr.onrender.com
# KEEP_ALIVE_URL=https://mcl-daak.onrender.com
CORS_ORIGINS=http://localhost:5173,https://mcl-ocr.vercel.app,https://mcl-ocr-git-main-yuvrajsingh0125.vercel.app
# CORS_ORIGINS=http://localhost:5173,https://mcl-daak.vercel.app,https://mcl-daak-git-duv-dev-shiv99.vercel.app
```

### Frontend
```text
VITE_API_URL=https://mcl-ocr.onrender.com
# VITE_API_URL=https://mcl-daak.onrender.com
```

## Google Sheets
- Two separate Apps Script deployments exist, one for dev and one for prod
- Monthly tabs are created automatically
- The sheet includes serial number, date, subject, summary, department, category, sender, receiver, reference number, filename, and processed timestamp

## Current technical debt
- Stale import in `config.py` line 1: `from anthropic.types import completion_create_params`
- `save_result_json()` still exists in `file_utils.py` but is unused
- Department and category lists are hardcoded in `claude_service.py`
- The service stack is still synchronous, so request handling blocks the event loop
- No file type or size validation exists yet on upload
- Multi-image OCR failure still fails the whole submission

## Priority order
1. Async refactor for network and CPU-bound service calls
2. Upload validation for type and size
3. Cleanup of dead code and stale imports
4. Better multi-image failure handling
5. Schema work in `schemas/`

## Communication preferences
- Explain what and why
- Be direct when something is wrong
- Keep recommendations minimal unless explicitly asked for more
