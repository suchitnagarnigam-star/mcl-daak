import os
import httpx
import base64
import math
from datetime import datetime, timezone
from dotenv import load_dotenv
from googleapiclient.discovery import build

# Load environment variables
load_dotenv()

from app.services.google_service import get_credentials
from app.config import supabase_client

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

def get_last_sync_time() -> int:
    try:
        query = supabase_client.table("email_sync_state").select("last_successful_sync").eq("id", 1).execute()
        if query.data and query.data[0].get("last_successful_sync"):
            iso_str = query.data[0]["last_successful_sync"]
            dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
            return int(dt.timestamp())
    except Exception as e:
        print(f"Error fetching last sync time: {e}")
    return 0

def update_last_sync_time(timestamp_sec: int):
    try:
        dt = datetime.fromtimestamp(timestamp_sec, tz=timezone.utc)
        iso_str = dt.isoformat()
        supabase_client.table("email_sync_state").upsert({"id": 1, "last_successful_sync": iso_str}).execute()
    except Exception as e:
        print(f"Error updating last sync time: {e}")

def is_duplicate(message_id: str) -> bool:
    try:
        query = supabase_client.table("document_submission").select("serial_number").eq("message_id", message_id).limit(1).execute()
        return len(query.data) > 0
    except Exception as e:
        return False

def sync_unread_emails():
    print("Authenticating with Google...")
    creds = get_credentials()
    if not creds:
        print("Failed to load credentials. Make sure token.json exists.")
        return

    service = build('gmail', 'v1', credentials=creds)

    last_sync = get_last_sync_time()
    print(f"Fetching emails from commissionermcl@gmail.com after timestamp {last_sync}...")
    
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
        print("No new emails found.")
        return

    webhook_secret = os.getenv("EMAIL_WEBHOOK_SECRET")
    local_url = "http://127.0.0.1:8000/classify-email/"
    
    max_timestamp_processed = last_sync

    for msg_ref in messages:
        msg_id = msg_ref['id']
        thread_id = msg_ref['threadId']
        
        print(f"\nProcessing Message ID: {msg_id}")
        
        msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
        
        # Get internalDate to update last_sync_time
        internal_date_ms = int(msg.get('internalDate', 0))
        internal_date_sec = math.floor(internal_date_ms / 1000)
        
        if internal_date_sec > max_timestamp_processed:
            max_timestamp_processed = internal_date_sec

        if is_duplicate(msg_id):
            print(f"  -> Message {msg_id} already exists in database. Skipping.")
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
        
        json_payload = {
            "message_id": msg_id,
            "thread_id": thread_id,
            "sender": sender,
            "subject": subject,
            "body": body or "No text body found.",
            "received_at": received_at
        }
        
        print(f"  -> Sending '{subject}' to local backend...")
        
        try:
            response = httpx.post(
                local_url,
                json=json_payload,
                headers={"x-email-webhook-secret": webhook_secret},
                timeout=60.0
            )
            
            if response.status_code == 200:
                print(f"  -> Success! Classified as: {response.json().get('extracted_data', {}).get('category', 'Unknown')}")
            else:
                print(f"  -> Failed: {response.status_code} - {response.text}")
                
        except Exception as e:
            print(f"  -> Error sending to local server: {e}")
            
    if max_timestamp_processed > last_sync:
        print(f"\nUpdating last_successful_sync in database...")
        update_last_sync_time(max_timestamp_processed)

if __name__ == "__main__":
    sync_unread_emails()
