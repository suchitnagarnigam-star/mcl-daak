# MCL Patr

MCL Patr is the Municipal Corporation Ludhiana document digitization system. It takes municipal correspondence, runs it through OpenCV preprocessing, Mistral OCR, Claude extraction, Supabase persistence, and Google Sheets sync, then returns structured data to the frontend.

## Current state

- Current working branch: `uv-dev`
- Dev remote: `origin` → `yuvrajsingh0125/MCL-OCR`
- Production remote: `daak` → `suchitnagarnigam-star/mcl-daak`
- Active OCR path: Mistral OCR only
- Active storage path: Supabase + Google Sheets
- The system is stateless on disk after OCR

## Live deployments

- Frontend dev: https://mcl-ocr.vercel.app
- Backend dev: https://mcl-ocr.onrender.com
- Frontend prod: https://mcl-daak.vercel.app
- Backend prod: https://mcl-daak.onrender.com

## Stack

| Layer | Technology | Purpose |
| --- | --- | --- |
| Frontend | React 19 + Vite + TypeScript | Scanner UI |
| Backend | FastAPI + Uvicorn | API and pipeline orchestration |
| Image processing | OpenCV | Preprocessing |
| OCR | Mistral OCR | Text extraction |
| Extraction | Anthropic Claude | Structured fields |
| Persistence | Supabase | Serial numbers and document storage |
| Archival | Google Sheets webhook | Long-term record archive |
| Deployment | Render + Vercel | Hosting |

## Pipeline

```text
Upload images
    ↓
Save temporarily to disk
    ↓
OpenCV preprocessing
    ↓
Mistral OCR per image
    ↓
Delete temp files immediately
    ↓
Combine OCR text in memory
    ↓
Claude extraction
    ↓
Supabase insert + serial number
    ↓
Google Sheets webhook sync
    ↓
Return structured response
```

## Extracted fields

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

`subject` and `summary` are required. `category` is now part of the stored and displayed result.

## Repository layout

```text
MCL-OCR/
├── backend/
│   └── app/
│       ├── main.py
│       ├── config.py
│       ├── routes/
│       ├── services/
│       ├── utils/
│       └── schemas/
├── frontend/
│   └── src/
│       ├── App.tsx
│       ├── components/
│       └── screens/
└── docs/
    ├── context_handoff.md
    ├── PROJECT_CONTEXT.md
    ├── CODEBASE_REPORT.md
    ├── DESIGN.md
    └── mcl_ui_prompt.md
```

## Branches

| Branch | Owner | Scope |
| --- | --- | --- |
| `main` | Both | Merged/deployed line |
| `uv-dev` | Yuvraj | Backend, LLM, routing, persistence, UI wiring |
| `frontend` | Arshdeep | Frontend camera and preprocessing work |

## What's working

- Multi-image upload pipeline
- Mistral OCR as the active OCR engine
- Claude extraction with 9 fields
- Supabase-backed history
- Google Sheets sync
- Result screen showing serial number and extracted data

## Next steps

1. Add upload validation.
2. Decide how partial OCR failures should behave.
3. Add Pydantic schemas.
4. Remove stale dead code and imports.
