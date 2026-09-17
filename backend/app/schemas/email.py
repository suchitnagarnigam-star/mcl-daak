from pydantic import BaseModel
from typing import Optional


class EmailIngestRequest(BaseModel):
    message_id: str
    thread_id: str
    sender: str
    subject: Optional[str] = ""
    body: str
    received_at: Optional[str] = None


class EmailIngestResponse(BaseModel):
    category: str
    is_grievance: bool
    serial_number: str
    summary: Optional[str] = None
    department: Optional[str] = None
