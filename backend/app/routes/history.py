from fastapi import APIRouter
from app.services.supabase_service import get_recent_documents

router = APIRouter(prefix="/history", tags=["history"])


@router.get("/")
def get_history():
    supabase_docs = get_recent_documents(limit=10)
    history_items = []

    for row in supabase_docs:
        llm_result = {
            "date": row.get("date"),
            "subject": row.get("subject"),
            "summary": row.get("summary"),
            "category": row.get("category"),
            "department": row.get("department"),
            "category": row.get("category"),
            "sender_name": row.get("sender_name"),
            "sender_contact": row.get("sender_contact"),
            "receiver": row.get("receiver"),
            "reference_number": row.get("reference_number"),
        }
        history_items.append(
            {
                "id": str(row.get("id") or row.get("serial_number")),
                "serial_number": row.get("serial_number"),
                "created_at": row.get("created_at") or "",
                "llm_result": llm_result,
                "ocr_text": "No raw text available",
            }
        )

    return history_items
