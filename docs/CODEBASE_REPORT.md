# MCL-OCR Codebase Report

**Last updated:** August 19, 2026

## Overview

This repository contains the active MCL document processing stack: FastAPI backend, OpenCV preprocessing, Mistral OCR, Claude extraction, Supabase persistence, and Google Sheets archival, paired with a React + Vite frontend.

The system is stateless on disk. Uploaded images are deleted after OCR, and no JSON output files are written. Supabase is the only persistence layer.

## Current repository structure

- `backend/`
  - `app/main.py` — FastAPI init, CORS, routers, keep-alive.
  - `app/config.py` — environment and client setup.
  - `app/routes/` — `upload`, `history`, `health`.
  - `app/services/` — OCR, extraction, preprocessing, Supabase, Sheets.
  - `app/utils/` — temporary file helpers.
  - `app/schemas/` — still empty.
- `frontend/`
  - `src/App.tsx` — app shell and routing.
  - `src/screens/` — Camera, Processing, Result, History.
  - `src/components/` — TopNav and DockNavigation.
  - `src/index.css` — global styles.
- `docs/` — current handoff and project analysis.

## Backend architecture

### Application entry
`backend/app/main.py` initializes FastAPI, configures CORS, and registers the upload, history, and health routers.

### Configuration and clients
`backend/app/config.py` wires Claude, Mistral, Supabase, and Google Sheets settings.

### Upload flow
`backend/app/routes/upload.py` is the core pipeline:

1. Validate the upload list.
2. Generate `submission_id` immediately.
3. Save each image temporarily, preprocess it, run Mistral OCR, and delete temp files.
4. Combine all OCR text with page markers.
5. Call Claude once on the combined document text.
6. Insert the result into Supabase and generate the serial number.
7. Push the final payload to Google Sheets.
8. Return the response without writing any file to disk.

### File handling
`backend/app/utils/file_utils.py` only handles temporary file save and delete operations in the active pipeline. `save_result_json()` still exists but is dead code.

### Persistence
`backend/app/services/supabase_service.py` generates serial numbers in the format `MCL/{year}/{number}` and writes rows into `document_submission`.

`backend/app/routes/history.py` reads the latest 10 records from Supabase and returns them as history items. Supabase is the source of truth.

### OCR and extraction
`backend/app/services/mistral_ocr_services.py` is the active OCR layer. `backend/app/services/claude_service.py` extracts 9 fields, including `category`.

## Frontend architecture

The frontend uses React 19, TypeScript, and Vite. The current screens are:

- `CameraScreen.tsx` — capture and upload.
- `ProcessingScreen.tsx` — stage tracker.
- `ResultScreen.tsx` — extracted data and serial number.
- `HistoryScreen.tsx` — recent submissions.

The app shell is centered around `App.tsx`, `TopNav.tsx`, and `DockNavigation.tsx`.

## Current status

### Fully implemented
- Multi-image upload pipeline.
- Temporary file deletion after OCR.
- Mistral OCR as the primary OCR engine.
- Claude extraction with 9 fields and `category`.
- Supabase serial generation and document storage.
- Google Sheets webhook sync.
- Supabase-backed history endpoint.
- Docker-based backend deployment.

### Planned or partial
- Human review/edit flow before final save.
- Pydantic schemas.
- Better multi-image failure handling.
- Input validation on upload size and type.
- Async refactor for blocking services.

## Technical stack summary

| Component | Technology | Purpose |
|-----------|------------|---------|
| Backend | FastAPI + Uvicorn | REST API server |
| Frontend | React 19 + Vite + TypeScript | Document scanner UI |
| Image processing | OpenCV | Preprocessing |
| OCR | Mistral OCR API | Text extraction |
| Extraction | Anthropic Claude | Structured field extraction |
| Persistence | Supabase (PostgreSQL) | Serial number generation and document storage |
| Archival | Google Sheets webhook | Long-term record archive |
| Deployment | Docker + Vercel + Render | Hosting |

## Key files by purpose

### Entry points
- `backend/app/main.py`
- `frontend/src/main.tsx`

### Core pipeline
- `backend/app/routes/upload.py`
- `backend/app/services/mistral_ocr_services.py`
- `backend/app/services/claude_service.py`
- `backend/app/services/opencv_services.py`
- `backend/app/services/supabase_service.py`
- `backend/app/services/sheets_service.py`

### History
- `backend/app/routes/history.py`
- `frontend/src/screens/HistoryScreen.tsx`

### Configuration
- `backend/app/config.py`
- `backend/requirements.txt`
- `frontend/.env`
- `frontend/.env.production`

## Next steps

1. Remove dead code and stale imports.
2. Add upload validation.
3. Add Pydantic schemas.
4. Decide multi-image partial failure behavior.
5. Keep the docs aligned with the current `uv-dev` and `daak` state.
