# Import httpx for making asynchronous HTTP requests
import httpx

# Import logging module for recording application events and errors
import logging
# Import datetime utilities for timestamp generation with timezone support
from datetime import datetime, timezone
# Import webhook URL and secret credentials from configuration
from app.config import SHEETS_WEBHOOK_URL, SHEETS_SECRET
from datetime import timezone, timedelta
IST = timezone(timedelta(hours=5, minutes=30))

# Initialize logger for this module to track events and errors
logger = logging.getLogger(__name__)

# Global variables to store the Google Sheets webhook URL and secret for authentication
SHEETS_WEBHOOK_URL = None 
SHEETS_SECRET = None


# Function to initialize/update the global Sheets webhook URL and secret credentials
# This allows dynamic configuration of the webhook endpoint and authentication secret
def init_sheets(webhook_url: str, secret: str):
    global SHEETS_WEBHOOK_URL, SHEETS_SECRET
    SHEETS_WEBHOOK_URL = webhook_url
    SHEETS_SECRET = secret


# Asynchronous function to push OCR results to Google Sheets via webhook
# Args: llm_result (dict) - Contains extracted data from OCR processing
#       filename (str) - Name of the file being processed
# Returns: bool - True if successfully pushed to Sheets, False otherwise
async def push_to_sheets(llm_result: dict, filename: str, serial_number: str) -> bool:
    # Check if webhook URL is configured; skip if not available
    if not SHEETS_WEBHOOK_URL:
        logger.warning("Sheets webhook URL not configured, skipping.")
        return False

    # Construct the payload to send to Google Sheets webhook
    # Includes: OCR results, filename, processing timestamp, and authentication secret
    payload = {
        "secret": SHEETS_SECRET,
        "data": {
            **llm_result,
            "serial_number": serial_number,
            "filename": filename,
            "processed_at": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
        }
    }

    try:
        # Create an async HTTP client with 10-second timeout and send POST request to webhook
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.post(SHEETS_WEBHOOK_URL, json=payload)
            # Check if response status is 200 (success)
            if resp.status_code == 200:
                logger.info("Sheets: row written successfully.")
                return True
            else:
                # Log error if webhook returned unexpected status code
                logger.error(f"Sheets: unexpected status {resp.status_code} — {resp.text}")
                return False
    # Catch any exceptions during HTTP request and log them
    except Exception as e:
        logger.error(f"Sheets: push failed — {e}")
        return False