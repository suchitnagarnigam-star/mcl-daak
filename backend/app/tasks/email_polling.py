"""
Email polling background task – uses Gmail API instead of IMAP.

Changes vs. old version:
- Calls fetch_emails_for_processing() which returns (message_id, content) tuples.
- After each successful email processing, marks the message as processed in Supabase.
- After each full poll cycle, persists last_successful_sync to Supabase.
- Adds exponential-backoff retry (up to MAX_RETRIES) for transient Gmail API errors.
- Structured logging with sync timestamps.
"""

import asyncio
import logging
from datetime import datetime, timezone
from uuid import uuid4

from app.config import EMAIL_POLL_INTERVAL
from app.services.email_service import fetch_emails_for_processing
from app.services.claude_service import process_document, is_municipal_grievance
from app.services.supabase_service import (
    insert_data,
    update_status,
    mark_gmail_message_processed,
    set_last_sync_timestamp,
)
from app.services.sheets_service import push_to_sheets

logger = logging.getLogger(__name__)

# Maximum number of retry attempts for transient errors during a single poll cycle
MAX_RETRIES = 3
# Base delay (seconds) for exponential backoff between retries
RETRY_BASE_DELAY = 5


async def process_email(email_content: str, submission_id: str) -> bool:
    """
    Process a single email through the full pipeline:
      1. Classify – is it a municipal grievance?
      2. Claude extraction
      3. Supabase insert
      4. Google Sheets sync
      5. Status update to 'complete'

    Returns True on success, False if the email was skipped or failed.
    """
    logger.info(f"[{submission_id}] Checking email relevance...")

    # 1. CLASSIFY – skip non-grievance emails
    if not is_municipal_grievance(email_content):
        logger.info(f"[{submission_id}] Email is NOT a municipal grievance. Skipping.")
        return False

    logger.info(f"[{submission_id}] Email IS a municipal grievance. Starting full processing...")

    # 2. CLAUDE EXTRACTION
    try:
        combined_text = (
            f"===== BEGIN EMAIL CONTENT =====\n\n{email_content}\n\n===== END EMAIL CONTENT ====="
        )
        llm_result = process_document(combined_text)

        if not llm_result or not llm_result.get("subject") or not llm_result.get("summary"):
            logger.warning(f"[{submission_id}] LLM extraction failed or missing required fields.")
            return False

        # Normalize null/empty fields to 'N/A'
        for field in ["date", "department", "sender_name", "sender_contact", "receiver", "reference_number"]:
            if not llm_result.get(field):
                llm_result[field] = "N/A"

        logger.info(f"[{submission_id}] LLM extraction complete.")

    except Exception as exc:
        logger.exception(f"[{submission_id}] Claude extraction failed: {exc}")
        return False

    # 3. SUPABASE INSERTION
    try:
        serial_number = insert_data(llm_result)
        logger.info(f"[{submission_id}] Inserted into Supabase: {serial_number}")
    except Exception as exc:
        logger.exception(f"[{submission_id}] Failed to insert into Supabase: {exc}")
        return False

    # 4. GOOGLE SHEETS SYNC
    try:
        sheets_filename = f"email_{submission_id}"
        await push_to_sheets(llm_result, sheets_filename, serial_number)
        logger.info(f"[{submission_id}] Google Sheets sync complete.")
    except Exception as exc:
        logger.exception(f"[{submission_id}] Google Sheets sync failed (data is saved): {exc}")
        # Non-fatal: data already in Supabase, continue to status update

    # 5. UPDATE STATUS TO COMPLETE
    try:
        update_status(serial_number, "complete")
        logger.info(f"[{submission_id}] Status updated to 'complete'.")
    except Exception as exc:
        logger.exception(f"[{submission_id}] Failed to update status: {exc}")

    return True


async def run_email_sync() -> dict:
    """
    Perform one full email sync cycle.
    Fetches new emails via Gmail API, processes grievances, marks messages
    as processed, and persists last_successful_sync.

    Returns a summary dict:
      { "fetched": int, "processed": int, "skipped": int, "errors": list[str] }
    """
    summary = {"fetched": 0, "processed": 0, "skipped": 0, "errors": []}
    now_utc = datetime.now(timezone.utc)

    # Fetch with exponential backoff retry
    email_tuples: list[tuple[str, str]] = []
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            email_tuples = fetch_emails_for_processing()
            break
        except Exception as exc:
            delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
            logger.warning(
                f"fetch_emails_for_processing failed (attempt {attempt}/{MAX_RETRIES}): {exc}. "
                f"Retrying in {delay}s..."
            )
            if attempt < MAX_RETRIES:
                await asyncio.sleep(delay)
            else:
                logger.error("All retry attempts exhausted. Skipping this poll cycle.")
                summary["errors"].append(str(exc))
                return summary

    summary["fetched"] = len(email_tuples)
    logger.info(f"Sync cycle: {len(email_tuples)} new email(s) to process.")

    for message_id, email_content in email_tuples:
        submission_id = str(uuid4())
        try:
            success = await process_email(email_content, submission_id)
            if success:
                summary["processed"] += 1
            else:
                summary["skipped"] += 1

            # Always mark as processed to prevent reprocessing on next cycle,
            # regardless of whether the email was a grievance or not.
            mark_gmail_message_processed(message_id)

        except Exception as exc:
            logger.exception(f"[{submission_id}] Unhandled error processing message {message_id}: {exc}")
            summary["errors"].append(f"{message_id}: {exc}")
            # Still mark as processed so we don't retry a permanently broken message
            mark_gmail_message_processed(message_id)

    # Persist last_successful_sync after the batch completes
    set_last_sync_timestamp(now_utc)
    logger.info(f"Sync state persisted. last_successful_sync = {now_utc.isoformat()}")

    return summary


async def start_email_polling():
    """
    Background task: periodically runs the Gmail sync cycle.
    Interval is configured via EMAIL_POLL_INTERVAL (seconds, default 3600).
    """
    logger.info(f"Email polling started. Interval: {EMAIL_POLL_INTERVAL}s ({EMAIL_POLL_INTERVAL // 60}m).")

    # Allow the server to fully boot before the first poll
    await asyncio.sleep(15)

    while True:
        cycle_start = datetime.now(timezone.utc)
        logger.info(f"[Poll cycle] Starting at {cycle_start.isoformat()}")

        try:
            summary = await run_email_sync()
            logger.info(
                f"[Poll cycle] Complete – "
                f"fetched={summary['fetched']}, "
                f"processed={summary['processed']}, "
                f"skipped={summary['skipped']}, "
                f"errors={len(summary['errors'])}"
            )
        except Exception as exc:
            logger.exception(f"[Poll cycle] Unexpected error in polling loop: {exc}")

        await asyncio.sleep(EMAIL_POLL_INTERVAL)
