from app.config import supabase_client
from datetime import datetime

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

