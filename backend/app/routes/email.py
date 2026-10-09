from fastapi import APIRouter, HTTPException, Header, Depends
import logging
import os
import base64
import math
from datetime import datetime, timezone

from googleapiclient.discovery import build
from app.services.google_service import get_credentials

from app.schemas.email import EmailIngestRequest, EmailIngestResponse
from app.services.claude_service import process_document
from app.services.supabase_service import (
    insert_data,
    update_status,
    find_submission_by_message_id,
    get_last_sync_time,
    update_last_sync_time,
    is_gmail_processed,
    mark_gmail_processed
)
from app.services.sheets_service import push_to_sheets
from app.services.google_service import (
    fetch_gmail_attachments,
    create_drive_folder,
    upload_to_drive
)

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

def get_email_body(payload):
    """Recursively extract the plain text body from the email payload."""
    if 'parts' in payload:
        for part in payload['parts']:
            if part['mimeType'] == 'text/plain':
                data = part['body'].get('data')
                if data:
                    return base64.urlsafe_b64decode(data).decode('utf-8')
            elif 'parts' in part:
                body = get_email_body(part)
                if body:
                    return body
    elif payload.get('mimeType') == 'text/plain':
        data = payload['body'].get('data')
        if data:
            return base64.urlsafe_b64decode(data).decode('utf-8')
    return ""


def _is_grievance(category: str) -> bool:
    return "grievance" in (category or "").lower()

def _process_attachments_to_drive(message_id: str, serial_number: str, llm_result: dict):
    try:
        attachments = fetch_gmail_attachments(message_id)
        if not attachments:
            return
            
        folder_id, folder_link = create_drive_folder(serial_number)
        if folder_id:
            success = upload_to_drive(folder_id, attachments)
            if success:
                llm_result["FILE_LOCATION"] = folder_link
            else:
                raise Exception("Drive upload function returned false.")
        else:
            raise Exception("Failed to create Drive folder.")
    except Exception as exc:
        logger.error(f"Failed to process attachments for {message_id}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to process and upload attachments to Google Drive.") from exc


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
    
    # Process attachments before pushing to sheets
    _process_attachments_to_drive(message_id, serial_number, llm_result)

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
    
    # Process attachments before pushing to sheets
    _process_attachments_to_drive(payload.message_id, serial_number, llm_result)
    
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

@router.post("/sync-gmail", dependencies=[Depends(verify_email_secret)])
async def sync_gmail_route():
    creds = get_credentials()
    if not creds:
        raise HTTPException(status_code=500, detail="Failed to load credentials.")

    service = build('gmail', 'v1', credentials=creds)

    sync_started_at = math.floor(datetime.now(timezone.utc).timestamp())
    last_sync = get_last_sync_time()
    
    q_str = "from:commissionermcl@gmail.com"
    if last_sync > 0:
        q_str += f" after:{last_sync}"
        
    messages = []
    request = service.users().messages().list(userId='me', q=q_str, maxResults=500)
    while request is not None:
        results = request.execute()
        messages.extend(results.get('messages', []))
        request = service.users().messages().list_next(request, results)

    if not messages:
        return {"message": "No new emails found.", "synced": 0}

    max_timestamp_processed = last_sync
    all_success = True

    for msg_ref in messages:
        msg_id = msg_ref['id']
        thread_id = msg_ref['threadId']
        
        msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
        
        internal_date_ms = int(msg.get('internalDate', 0))
        internal_date_sec = math.floor(internal_date_ms / 1000)
        
        if not (last_sync < internal_date_sec <= sync_started_at):
            continue

        if is_gmail_processed(msg_id):
            continue
            
        payload = msg['payload']
        headers = payload['headers']
            
        sender = ""
        subject = ""
        received_at = ""
        
        for header in headers:
            if header['name'] == 'From':
                sender = header['value']
            elif header['name'] == 'Subject':
                subject = header['value']
            elif header['name'] == 'Date':
                received_at = header['value']
                
        body = get_email_body(payload)
        
        ingest_payload = EmailIngestRequest(
            message_id=msg_id,
            thread_id=thread_id,
            sender=sender,
            subject=subject,
            body=body or "No text body found.",
            received_at=received_at
        )

        try:
            await classify_email_route(ingest_payload)
            mark_gmail_processed(msg_id)
            if internal_date_sec > max_timestamp_processed:
                max_timestamp_processed = internal_date_sec
            
            # Sleep to avoid hitting the Gemini Free Tier 15 RPM rate limit
            import asyncio
            await asyncio.sleep(4.5)
            
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                logger.warning(f"Rate limit hit on message {msg_id}. Sleeping for 60 seconds...")
                import asyncio
                await asyncio.sleep(60)
            else:
                logger.error(f"Failed processing message {msg_id}: {e}")
            all_success = False
            break

    if all_success and max_timestamp_processed > last_sync:
        update_last_sync_time(max_timestamp_processed)

    return {"message": "Sync complete.", "max_timestamp": max_timestamp_processed, "success": all_success}
