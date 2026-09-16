from app.config import supabase_client
from datetime import datetime, timezone

def insert_data(llm_result):
    current_year = datetime.now().year
    pattern = f"MCL/{current_year}/%"

    # we are going to insert the data into the database
    # first we need to check if there is any serial_number that start with MCL/{current_year}/
    query = supabase_client.table("document_submission").select("serial_number").like("serial_number", pattern).execute()

    # find max serial_number
    if query.data:
        # here we are only extracting the last part of the serial_number which is the number itself from all the available data
        numbers = [int(item["serial_number"].split('/')[-1]) for item in query.data]
        max_serial_number = max(numbers)    
    else:
        max_serial_number = 1000

    next_serial_number = max_serial_number + 1
    new_serial_number = f"MCL/{current_year}/{next_serial_number}"

    # after the serial number we here insert the data into the database
    supabase_client.table("document_submission").insert({
    "serial_number": new_serial_number,
    "status": "pending",
    "date" : llm_result["date"],
    "subject" : llm_result["subject"],
    "summary" : llm_result["summary"],
    "sender_name" : llm_result["sender_name"],
    "department" : llm_result["department"],
    "category":llm_result["category"],
    "sender_contact": llm_result["sender_contact"],
    "receiver": llm_result["receiver"],
    "reference_number": llm_result["reference_number"]
    }).execute()    

    return new_serial_number


def get_recent_documents(limit: int = 10):
    if not supabase_client:
        return []
    try:
        query = (
            supabase_client.table("document_submission")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return query.data or []
    except Exception as e:
        print(f"Error fetching recent documents from Supabase: {e}")
        return []
    
def update_status(serial_number: str, status: str):
    supabase_client.table("document_submission").update({"status": status}).eq("serial_number", serial_number).execute()


# ==============================================================
# Gmail deduplication helpers
# ==============================================================

def is_gmail_message_processed(message_id: str) -> bool:
    """Return True if this Gmail message_id was already processed."""
    if not supabase_client:
        return False
    try:
        result = (
            supabase_client.table("processed_gmail_messages")
            .select("message_id")
            .eq("message_id", message_id)
            .limit(1)
            .execute()
        )
        return bool(result.data)
    except Exception as e:
        # If the table doesn't exist yet, treat as not-processed so we don't silently drop emails
        print(f"[supabase] is_gmail_message_processed error: {e}")
        return False


def mark_gmail_message_processed(message_id: str) -> None:
    """Insert message_id into the deduplication table. Ignores conflicts."""
    if not supabase_client:
        return
    try:
        supabase_client.table("processed_gmail_messages").upsert(
            {"message_id": message_id},
            on_conflict="message_id",
        ).execute()
    except Exception as e:
        print(f"[supabase] mark_gmail_message_processed error: {e}")


# ==============================================================
# Sync-state helpers (last_successful_sync persistence)
# ==============================================================

def get_last_sync_timestamp() -> datetime | None:
    """Read the singleton last_successful_sync row from email_sync_state."""
    if not supabase_client:
        return None
    try:
        result = (
            supabase_client.table("email_sync_state")
            .select("last_successful_sync")
            .eq("id", 1)
            .limit(1)
            .execute()
        )
        if result.data and result.data[0].get("last_successful_sync"):
            raw = result.data[0]["last_successful_sync"]
            # Supabase returns ISO strings; parse to aware datetime
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return dt.astimezone(timezone.utc)
        return None
    except Exception as e:
        print(f"[supabase] get_last_sync_timestamp error: {e}")
        return None


def set_last_sync_timestamp(ts: datetime) -> None:
    """Persist the last_successful_sync singleton row."""
    if not supabase_client:
        return
    try:
        supabase_client.table("email_sync_state").upsert(
            {"id": 1, "last_successful_sync": ts.isoformat()},
            on_conflict="id",
        ).execute()
    except Exception as e:
        print(f"[supabase] set_last_sync_timestamp error: {e}")


