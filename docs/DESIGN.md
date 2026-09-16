# MCL Patr — Design Document

Architecture decisions and the reasoning behind them.

## 1. Why the pipeline is split into OCR, extraction, storage, and sync

OCR and structured extraction are different problems.

- OCR turns pixels into text.
- Claude turns OCR text into structured fields.
- Supabase stores the result and generates serial numbers.
- Google Sheets acts as the archival mirror.

Keeping those steps separate makes it easier to debug where a failure happened and lets each layer evolve independently.

## 2. Why Mistral OCR is the active OCR engine

The current deployment path uses Mistral OCR only. The repository no longer treats PaddleOCR as an active fallback in the production flow.

That keeps the runtime simpler and avoids carrying a second OCR stack that is no longer part of the current plan.

## 3. Why Claude receives combined OCR text

The backend concatenates the per-image OCR results with page markers and sends Claude a single combined document.

That decision matters because the extracted fields describe the document as a whole, not a single page. Running Claude once reduces contradictory field values across pages and keeps the extraction model focused on document-level context.

## 4. Why identifiers are generated server-side

`submission_id` is generated when FastAPI receives the request, and `serial_number` is generated in Supabase.

This avoids trusting the client for identity and keeps the submission traceable even when processing fails partway through.

## 5. Why temp files are deleted immediately

Temporary upload and processed files are removed right after OCR completes.

That matches the project constraint that the system should be stateless on disk after processing and keeps the server from accumulating sensitive correspondence images.

## 6. Why the category field exists

The current extracted payload includes `category` alongside the other structured fields.

That field is now part of the backend response, Supabase record, history payload, and result UI. It is not just a display-only label.

## 7. Open risks

- Multi-image partial failure behavior is still not defined.
- Upload validation for size and type is still missing.
- The service stack is synchronous and still blocks the event loop.
- Department and category classification lists are still hardcoded in Claude prompt logic.

## 8. Design constraints that still hold

| Constraint | Reason |
|---|---|
| No permanent image storage | The documents may contain sensitive municipal correspondence. |
| No streaming | The output is a small structured response; streaming adds complexity without a real UX gain. |
| No agents | The pipeline is deterministic and fixed. |
| No auth / RBAC yet | MVP scope and local workflow assumptions. |

## 9. Near-term direction

1. Add upload validation.
2. Decide the multi-image failure policy.
3. Move blocking work off the event loop.
4. Add schemas for request and response validation.
5. Keep the docs aligned with the current `uv-dev` and `daak` state.
