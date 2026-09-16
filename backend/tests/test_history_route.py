from app.routes import history


def test_get_history_includes_category(monkeypatch):
    sample_rows = [
        {
            "id": "abc123",
            "serial_number": "S-1",
            "created_at": "2026-08-19T00:00:00Z",
            "date": "2026-08-19",
            "subject": "Street lights",
            "summary": "Lights are not working",
            "category": "Service Request",
            "department": "Lights / Electrical Branch",
            "sender_name": "Citizen",
            "sender_contact": "9999999999",
            "receiver": "Commissioner",
            "reference_number": "REF-1",
        }
    ]
    monkeypatch.setattr(history, "get_recent_documents", lambda limit: sample_rows)

    response = history.get_history()

    assert response[0]["llm_result"]["category"] == "Service Request"
