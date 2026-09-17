from fastapi import APIRouter, HTTPException, Header, Depends
import logging
import os

from app.schemas.email import EmailIngestRequest, EmailIngestResponse
from app.services.claude_service import process_document
from app.services.supabase_service import (
    insert_data,
    update_status,
    find_submission_by_message_id,
)
from app.services.sheets_service import push_to_sheets

logger = logging.getLogger(__name__)

EMAIL_WEBHOOK_SECRET = os.getenv("EMAIL_WEBHOOK_SECRET")

router = APIRouter(
    prefix="/classify-email",
    tags=["Email Classification"],
)

STORED_FIELDS = [
    "date", "subject", "summary", "department", "category",
    "sender_name", "sender_contact", "receiver", "reference_number",
]


def verify_email_secret(x_email_webhook_secret: str = Header(default=None)):
    if not EMAIL_WEBHOOK_SECRET or x_email_webhook_secret != EMAIL_WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing webhook secret.")


def _is_grievance(category: str) -> bool:
    return "grievance" in (category or "").lower()


def _response_from_row(row: dict) -> EmailIngestResponse:
    return EmailIngestResponse(
        category=row.get("category") or "N/A",
        is_grievance=_is_grievance(row.get("category")),
        serial_number=row["serial_number"],
        summary=row.get("summary"),
        department=row.get("department"),
    )


def _is_duplicate_key_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "duplicate key" in message or "23505" in message or "unique constraint" in message


async def _retry_pending_submission(existing: dict, message_id: str) -> EmailIngestResponse:
    llm_result = {field: existing.get(field) for field in STORED_FIELDS}
    serial_number = existing["serial_number"]
    filename = f"gmail:{message_id}"

    push_success = await push_to_sheets(llm_result, filename, serial_number)
    if not push_success:
        raise HTTPException(
            status_code=500,
            detail="Email record exists but Google Sheets sync is still failing; will retry.",
        )

    update_status(serial_number, "complete")
    return _response_from_row({**existing, "serial_number": serial_number})


@router.post("/", response_model=EmailIngestResponse, dependencies=[Depends(verify_email_secret)])
async def classify_email_route(payload: EmailIngestRequest):

    # Deduplication: never reprocess or re-insert the same Gmail message.
    existing = find_submission_by_message_id(payload.message_id)
    if existing:
        if existing.get("status") == "complete":
            return _response_from_row(existing)
        return await _retry_pending_submission(existing, payload.message_id)

    combined_text = (
        f"From: {payload.sender}\n"
        f"Subject: {payload.subject or ''}\n"
        f"Date: {payload.received_at or ''}\n\n"
        f"{payload.body}"
    )

    try:
        llm_result = process_document(combined_text)
    except Exception as exc:
        logger.exception("Email classification failed for message %s: %s", payload.message_id, exc)
        raise HTTPException(status_code=500, detail="Classification failed.") from exc

    if llm_result.get("error"):
        raise HTTPException(status_code=502, detail=llm_result.get("error"))

    if not llm_result.get("subject") or not llm_result.get("summary"):
        raise HTTPException(
            status_code=422,
            detail={"message": "Failed to extract subject or summary from email.", "status": "failed"},
        )

    # Normalize missing fields to N/A, except reference_number which falls
    # back to a Gmail permalink so the record stays traceable to its source.
    # category is included here too: Claude legitimately returns null when
    # nothing in the 15-item list fits (e.g. spam/marketing email), and
    # EmailIngestResponse requires a non-null string.
    for field in ["date", "department", "category", "sender_name", "sender_contact", "receiver"]:
        if not llm_result.get(field):
            llm_result[field] = "N/A"

    if not llm_result.get("reference_number"):
        llm_result["reference_number"] = f"https://mail.google.com/mail/u/0/#all/{payload.thread_id}"

    try:
        serial_number = insert_data(llm_result, payload.message_id)
    except Exception as exc:
        if _is_duplicate_key_error(exc):
            existing = find_submission_by_message_id(payload.message_id)
            if existing:
                if existing.get("status") == "complete":
                    return _response_from_row(existing)
                return await _retry_pending_submission(existing, payload.message_id)
        logger.exception("Failed to insert email submission for message %s: %s", payload.message_id, exc)
        raise HTTPException(status_code=500, detail="Failed to insert data into database.") from exc

    filename = f"gmail:{payload.message_id}"
    push_success = await push_to_sheets(llm_result, filename, serial_number)
    if not push_success:
        raise HTTPException(
            status_code=500,
            detail="Email processed but Google Sheets sync failed.",
        )

    update_status(serial_number, "complete")

    return EmailIngestResponse(
        category=llm_result["category"],
        is_grievance=_is_grievance(llm_result["category"]),
        serial_number=serial_number,
        summary=llm_result.get("summary"),
        department=llm_result.get("department"),
    )
