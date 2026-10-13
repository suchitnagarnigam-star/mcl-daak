import asyncio

import pytest
from fastapi import HTTPException

from app.routes import email
from app.schemas.email import EmailIngestRequest

DRIVE_LINK = "https://drive.google.com/drive/folders/abc123"


def _payload(**overrides):
    data = {
        "message_id": "msg1",
        "thread_id": "thread1",
        "sender": "Citizen <citizen@example.com>",
        "subject": "Broken streetlight",
        "body": "The streetlight on my road is broken.",
        "received_at": "2026-10-13T10:00:00Z",
    }
    data.update(overrides)
    return EmailIngestRequest(**data)


@pytest.fixture
def calls(monkeypatch):
    """Replace every external dependency of the route and record what it was given."""
    record = {"insert": [], "push": [], "status": []}

    monkeypatch.setattr(email, "find_submission_by_message_id", lambda message_id: None)
    monkeypatch.setattr(
        email,
        "process_document",
        lambda text: {
            "date": "2026-10-13",
            "subject": "Broken streetlight",
            "summary": "A streetlight is broken.",
            "department": "Lights / Electrical Branch",
            "category": "Public Grievance",
            "sender_name": "Citizen",
            "sender_contact": "citizen@example.com",
            "receiver": "Commissioner",
            "reference_number": None,
        },
    )

    def fake_insert(llm_result, message_id=None, attachments_link=None):
        record["insert"].append({"message_id": message_id, "attachments_link": attachments_link})
        return "MCL/2026/1001"

    async def fake_push(llm_result, filename, serial_number):
        record["push"].append({"filename": filename, "serial_number": serial_number, "data": llm_result})
        return record.get("push_ok", True)

    monkeypatch.setattr(email, "insert_data", fake_insert)
    monkeypatch.setattr(email, "push_to_sheets", fake_push)
    monkeypatch.setattr(email, "update_status", lambda serial, status: record["status"].append((serial, status)))
    return record


def _run(payload):
    return asyncio.run(email.classify_email_route(payload))


def test_email_without_attachments_behaves_as_before(calls):
    response = _run(_payload())

    assert response.serial_number == "MCL/2026/1001"
    assert response.is_grievance is True
    assert calls["insert"] == [{"message_id": "msg1", "attachments_link": None}]
    assert calls["push"][0]["filename"] == "Email"
    assert "FILE_LOCATION" not in calls["push"][0]["data"]
    assert calls["status"] == [("MCL/2026/1001", "complete")]


def test_drive_link_is_stored_and_sent_to_the_sheet_attachment_column(calls):
    _run(_payload(attachments_link=DRIVE_LINK))

    assert calls["insert"] == [{"message_id": "msg1", "attachments_link": DRIVE_LINK}]
    assert calls["push"][0]["data"]["FILE_LOCATION"] == DRIVE_LINK
    assert calls["push"][0]["filename"] == "Email"


def test_the_sheet_copy_does_not_change_what_is_stored(calls):
    # The link is added to a copy for the Sheet only; the extracted fields
    # themselves are untouched.
    _run(_payload(attachments_link=DRIVE_LINK))

    sent = dict(calls["push"][0]["data"])
    sent.pop("FILE_LOCATION")
    assert sent["subject"] == "Broken streetlight"
    assert sent["category"] == "Public Grievance"


@pytest.mark.parametrize(
    "bad_link",
    [
        "https://evil.example.com/drive.google.com/",
        "http://drive.google.com/drive/folders/abc123",
        '=HYPERLINK("https://drive.google.com/x","open")',
        "https://drive.google.com/drive/folders/abc\n123",
        "   ",
    ],
)
def test_non_drive_links_are_ignored_and_do_not_block_the_record(calls, bad_link):
    response = _run(_payload(attachments_link=bad_link))

    assert response.serial_number == "MCL/2026/1001"
    assert calls["insert"] == [{"message_id": "msg1", "attachments_link": None}]
    assert calls["push"][0]["filename"] == "Email"
    assert "FILE_LOCATION" not in calls["push"][0]["data"]


def test_retry_of_a_pending_record_uses_the_link_and_completes(calls, monkeypatch):
    pending = {
        "serial_number": "MCL/2026/1005",
        "status": "pending",
        "category": "Public Grievance",
        "summary": "A streetlight is broken.",
        "department": "Lights / Electrical Branch",
    }
    monkeypatch.setattr(email, "find_submission_by_message_id", lambda message_id: pending)

    response = _run(_payload(attachments_link=DRIVE_LINK))

    assert response.serial_number == "MCL/2026/1005"
    assert calls["insert"] == []
    assert len(calls["push"]) == 1
    assert calls["push"][0]["serial_number"] == "MCL/2026/1005"
    assert calls["push"][0]["filename"] == "Email"
    assert calls["push"][0]["data"]["FILE_LOCATION"] == DRIVE_LINK
    assert calls["status"] == [("MCL/2026/1005", "complete")]


def test_retry_prefers_the_link_already_stored_on_the_record(calls, monkeypatch):
    stored = "https://drive.google.com/drive/folders/stored999"
    pending = {
        "serial_number": "MCL/2026/1005",
        "status": "pending",
        "category": "Public Grievance",
        "attachments_link": stored,
    }
    monkeypatch.setattr(email, "find_submission_by_message_id", lambda message_id: pending)

    _run(_payload(attachments_link=DRIVE_LINK))

    assert calls["push"][0]["data"]["FILE_LOCATION"] == stored


def test_already_complete_record_is_returned_without_reprocessing(calls, monkeypatch):
    done = {"serial_number": "MCL/2026/1009", "status": "complete", "category": "General Correspondence"}
    monkeypatch.setattr(email, "find_submission_by_message_id", lambda message_id: done)

    response = _run(_payload(attachments_link=DRIVE_LINK))

    assert response.serial_number == "MCL/2026/1009"
    assert calls["insert"] == []
    assert calls["push"] == []


def test_sheet_failure_is_still_an_error_and_not_marked_complete(calls):
    calls["push_ok"] = False

    with pytest.raises(HTTPException) as excinfo:
        _run(_payload(attachments_link=DRIVE_LINK))

    assert excinfo.value.status_code == 500
    assert calls["status"] == []
