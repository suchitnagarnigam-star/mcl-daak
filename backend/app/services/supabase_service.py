from app.config import supabase_client
from datetime import datetime, timezone

def insert_data(llm_result, message_id=None):
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
    row = {
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
        "reference_number": llm_result["reference_number"],
    }
    if message_id is not None:
        row["message_id"] = message_id

    supabase_client.table("document_submission").insert(row).execute()

    return new_serial_number


def find_submission_by_message_id(message_id: str):
    query = (
        supabase_client.table("document_submission")
        .select("*")
        .eq("message_id", message_id)
        .limit(1)
        .execute()
    )
    if query.data:
        return query.data[0]
    return None


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

def get_last_sync_time() -> int:
    if not supabase_client: return 0
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
    if not supabase_client: return
    try:
        dt = datetime.fromtimestamp(timestamp_sec, tz=timezone.utc)
        iso_str = dt.isoformat()
        supabase_client.table("email_sync_state").upsert({"id": 1, "last_successful_sync": iso_str}).execute()
    except Exception as e:
        print(f"Error updating last sync time: {e}")

def is_gmail_processed(message_id: str) -> bool:
    if not supabase_client: return False
    try:
        query = supabase_client.table("processed_gmail_messages").select("message_id").eq("message_id", message_id).limit(1).execute()
        return len(query.data) > 0
    except Exception as e:
        return False

def mark_gmail_processed(message_id: str):
    if not supabase_client: return
    try:
        supabase_client.table("processed_gmail_messages").insert({"message_id": message_id}).execute()
    except Exception as e:
        print(f"Error marking gmail processed: {e}")

