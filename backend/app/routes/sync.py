"""
Manual email sync endpoint.

POST /sync/email
    Triggers an immediate Gmail fetch + processing cycle using the same
    pipeline as the background polling task.

    Response:
    {
        "fetched": 3,
        "processed": 2,
        "skipped": 1,
        "errors": [],
        "sync_triggered_at": "2026-09-16T05:00:00+00:00"
    }
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.tasks.email_polling import run_email_sync

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sync", tags=["Sync"])


@router.post("/email")
async def manual_email_sync():
    """
    Trigger an immediate Gmail email sync cycle.

    This runs the exact same pipeline as the background poller:
    - Fetches emails since last_successful_sync (minus overlap)
    - Classifies, extracts, inserts into Supabase, and syncs to Google Sheets
    - Marks messages as processed and persists last_successful_sync
    """
    triggered_at = datetime.now(timezone.utc)
    logger.info(f"Manual sync triggered at {triggered_at.isoformat()}")

    try:
        summary = await run_email_sync()
    except Exception as exc:
        logger.exception(f"Manual sync failed: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Email sync failed: {exc}",
        )

    return {
        **summary,
        "sync_triggered_at": triggered_at.isoformat(),
    }
