"""
Gmail API email fetching service – OAuth 2.0 (offline refresh token).

Replaces the old IMAP-based implementation.

Key public API
--------------
fetch_emails_for_processing() -> list[tuple[str, str]]
    Returns a list of (gmail_message_id, formatted_email_content) tuples for
    all emails that arrived since last_successful_sync (minus overlap window),
    skipping any that are already recorded in the processed_gmail_messages table.
"""

import base64
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from email import message_from_bytes
from email.header import decode_header as _decode_header
from pathlib import Path
from typing import Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from app.config import (
    GMAIL_CREDENTIALS_FILE,
    GMAIL_TOKEN_FILE,
    GMAIL_USER,
    GMAIL_SYNC_OVERLAP_MINUTES,
)
from app.services.supabase_service import get_last_sync_timestamp

logger = logging.getLogger(__name__)

# Scopes required: read-only access to Gmail messages
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# How many messages to request per page (max allowed by Gmail API is 500)
_PAGE_SIZE = 100


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def build_gmail_service():
    """
    Build and return an authenticated Gmail API service object.

    Token refresh is handled automatically by the google-auth library.
    If token.json is missing or invalid, raises FileNotFoundError so the
    caller can log a helpful message rather than crashing silently.
    """
    creds: Optional[Credentials] = None

    token_path = Path(GMAIL_TOKEN_FILE) if GMAIL_TOKEN_FILE else Path("token.json")
    creds_path = Path(GMAIL_CREDENTIALS_FILE) if GMAIL_CREDENTIALS_FILE else Path("credentials.json")

    # Load saved token
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), GMAIL_SCOPES)

    # Refresh or re-authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Gmail token expired – refreshing automatically.")
            creds.refresh(Request())
        else:
            # token.json is missing or has no refresh_token
            if not creds_path.exists():
                raise FileNotFoundError(
                    f"Gmail credentials file not found: {creds_path.resolve()}. "
                    "Download credentials.json from Google Cloud Console."
                )
            raise FileNotFoundError(
                f"Gmail token file not found or invalid: {token_path.resolve()}. "
                "Run `python generate_token.py` once to generate it."
            )

        # Persist refreshed token
        token_path.write_text(creds.to_json())

    return build("gmail", "v1", credentials=creds)


# ---------------------------------------------------------------------------
# Header decoding helpers
# ---------------------------------------------------------------------------

def _decode_mime_header(raw: Optional[str]) -> str:
    """Safely decode a MIME-encoded email header into a plain UTF-8 string."""
    if not raw:
        return ""
    parts = []
    for fragment, encoding in _decode_header(raw):
        if isinstance(fragment, bytes):
            parts.append(fragment.decode(encoding or "utf-8", errors="replace"))
        else:
            parts.append(fragment)
    return "".join(parts)


# ---------------------------------------------------------------------------
# Message body extraction
# ---------------------------------------------------------------------------

def _extract_body_from_raw(raw_bytes: bytes) -> str:
    """
    Parse a raw RFC-822 email bytes object and return the plain-text body.
    Falls back to HTML-stripped content if no text/plain part is found.
    """
    msg = message_from_bytes(raw_bytes)

    plain_parts: list[str] = []
    html_parts: list[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in disposition:
                continue
            payload_bytes = part.get_payload(decode=True)
            if not payload_bytes:
                continue
            charset = part.get_content_charset() or "utf-8"
            text = payload_bytes.decode(charset, errors="replace")
            if ct == "text/plain":
                plain_parts.append(text)
            elif ct == "text/html":
                html_parts.append(text)
    else:
        payload_bytes = msg.get_payload(decode=True)
        if payload_bytes:
            charset = msg.get_content_charset() or "utf-8"
            text = payload_bytes.decode(charset, errors="replace")
            if msg.get_content_type() == "text/plain":
                plain_parts.append(text)
            else:
                html_parts.append(text)

    if plain_parts:
        return "\n".join(plain_parts).strip()

    # Strip basic HTML tags as a last resort
    if html_parts:
        raw_html = "\n".join(html_parts)
        return re.sub(r"<[^>]+>", " ", raw_html).strip()

    return ""


def _extract_body_from_payload(payload: dict) -> str:
    """
    Recursively extract plain-text body from a Gmail API message payload dict
    (used when the full raw RFC-822 bytes are not available).
    """
    mime_type = payload.get("mimeType", "")
    parts = payload.get("parts", [])

    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")

    if mime_type == "text/html" and not parts:
        data = payload.get("body", {}).get("data", "")
        if data:
            raw_html = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
            return re.sub(r"<[^>]+>", " ", raw_html).strip()

    # Recurse into parts
    for part in parts:
        result = _extract_body_from_payload(part)
        if result:
            return result

    return ""


# ---------------------------------------------------------------------------
# Single message parsing
# ---------------------------------------------------------------------------

def parse_gmail_message(service, message_id: str) -> Optional[str]:
    """
    Fetch a single Gmail message by ID and return a formatted string
    compatible with the existing Claude processing pipeline:

        Subject: ...
        From: ...
        Date: ...

        <body>

    Returns None if the message cannot be fetched or parsed.
    """
    try:
        # Prefer 'raw' format to reuse existing MIME parsing logic
        msg_data = (
            service.users()
            .messages()
            .get(userId="me", id=message_id, format="raw")
            .execute()
        )
        raw_encoded = msg_data.get("raw", "")
        if not raw_encoded:
            logger.warning(f"[{message_id}] Empty raw payload from Gmail API.")
            return None

        raw_bytes = base64.urlsafe_b64decode(raw_encoded + "==")
        parsed = message_from_bytes(raw_bytes)

        subject = _decode_mime_header(parsed.get("Subject", "(No Subject)"))
        sender = _decode_mime_header(parsed.get("From", ""))
        date_str = parsed.get("Date", "")
        body = _extract_body_from_raw(raw_bytes)

        content = f"Subject: {subject}\nFrom: {sender}\nDate: {date_str}\n\n{body}"
        return content

    except HttpError as e:
        logger.error(f"[{message_id}] Gmail API HttpError while fetching message: {e}")
        return None
    except Exception as e:
        logger.exception(f"[{message_id}] Unexpected error parsing message: {e}")
        return None


# ---------------------------------------------------------------------------
# Listing messages with timestamp filter + pagination
# ---------------------------------------------------------------------------

def _build_gmail_query(since_dt: datetime) -> str:
    """
    Build a Gmail search query that fetches all messages (read + unread)
    received on or after *since_dt*.

    Gmail's `after:` operator uses Unix epoch seconds (UTC).
    """
    epoch_seconds = int(since_dt.timestamp())
    return f"after:{epoch_seconds}"


def fetch_message_ids_since(service, since_dt: datetime) -> list[str]:
    """
    Return a list of Gmail message IDs for all messages received since *since_dt*.
    Handles pagination automatically.
    """
    query = _build_gmail_query(since_dt)
    logger.info(f"Gmail query: '{query}'")

    message_ids: list[str] = []
    page_token: Optional[str] = None
    page_number = 0

    while True:
        page_number += 1
        try:
            kwargs: dict = {
                "userId": "me",
                "q": query,
                "maxResults": _PAGE_SIZE,
            }
            if page_token:
                kwargs["pageToken"] = page_token

            response = service.users().messages().list(**kwargs).execute()
            messages = response.get("messages", [])
            message_ids.extend(m["id"] for m in messages)
            logger.debug(f"Page {page_number}: got {len(messages)} messages (total so far: {len(message_ids)})")

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        except HttpError as e:
            logger.error(f"Gmail API HttpError listing messages (page {page_number}): {e}")
            break
        except Exception as e:
            logger.exception(f"Unexpected error listing messages (page {page_number}): {e}")
            break

    logger.info(f"Total message IDs found: {len(message_ids)}")
    return message_ids


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def fetch_emails_for_processing() -> list[tuple[str, str]]:
    """
    Orchestrate the full Gmail fetch pipeline.

    Steps:
    1. Load last_successful_sync from Supabase (falls back to 24 h ago if never set).
    2. Subtract GMAIL_SYNC_OVERLAP_MINUTES for reliability.
    3. Query Gmail API for all message IDs since that timestamp (read + unread).
    4. For each message ID, check the deduplication table – skip if already processed.
    5. Parse each new message into a formatted content string.
    6. Return list of (message_id, content) tuples.

    Callers are responsible for:
    - Calling mark_gmail_message_processed(message_id) after successful handling.
    - Calling set_last_sync_timestamp(now) after the batch completes.
    """
    if not GMAIL_USER:
        logger.error("GMAIL_USER is not configured. Cannot fetch emails.")
        return []

    # 1. Determine the fetch window start
    last_sync = get_last_sync_timestamp()
    now_utc = datetime.now(timezone.utc)

    if last_sync is None:
        # First run: look back 24 hours
        since_dt = now_utc - timedelta(hours=24)
        logger.info("No previous sync timestamp found. Fetching emails from the last 24 hours.")
    else:
        overlap = timedelta(minutes=GMAIL_SYNC_OVERLAP_MINUTES)
        since_dt = last_sync - overlap
        logger.info(
            f"Fetching emails since {since_dt.isoformat()} "
            f"(last_sync={last_sync.isoformat()}, overlap={GMAIL_SYNC_OVERLAP_MINUTES}m)"
        )

    # 2. Build Gmail service
    try:
        service = build_gmail_service()
    except FileNotFoundError as e:
        logger.error(f"Gmail authentication failed: {e}")
        return []
    except Exception as e:
        logger.exception(f"Unexpected error building Gmail service: {e}")
        return []

    # 3. Fetch message IDs
    message_ids = fetch_message_ids_since(service, since_dt)
    if not message_ids:
        logger.info("No new messages found in the fetch window.")
        return []

    # 4 & 5. Deduplicate and parse
    # Import here to avoid circular imports (supabase_service -> config -> ...)
    from app.services.supabase_service import is_gmail_message_processed

    results: list[tuple[str, str]] = []
    skipped_count = 0

    for msg_id in message_ids:
        if is_gmail_message_processed(msg_id):
            skipped_count += 1
            logger.debug(f"[{msg_id}] Already processed – skipping.")
            continue

        content = parse_gmail_message(service, msg_id)
        if content:
            results.append((msg_id, content))
        else:
            logger.warning(f"[{msg_id}] Could not parse message – skipping.")

    logger.info(
        f"fetch_emails_for_processing complete: "
        f"{len(results)} to process, {skipped_count} skipped (already processed), "
        f"{len(message_ids) - len(results) - skipped_count} parse failures."
    )
    return results
