import json
from pathlib import Path
from types import SimpleNamespace

from inquiry_processor import InquiryStore, classify_with_gpt, process_unread


class FakeMailbox:
    def __init__(self, messages):
        self.messages = messages
        self.replies = []
        self.read = []

    def unread_messages(self):
        return self.messages

    def has_replied(self, message):
        return message.get("already_replied", False)

    def reply(self, message_id):
        self.replies.append(message_id)

    def mark_read(self, message_id):
        self.read.append(message_id)


def test_processes_inquiry_and_ignores_other_email(tmp_path):
    messages = [{"id": "1", "from": {"emailAddress": {"address": "buyer@example.com"}}}, {"id": "2"}]
    mailbox = FakeMailbox(messages)
    classifications = iter([
        {"is_inquiry": True, "company_name": "Buyer Co", "contact_person": "Asha", "email": "", "phone": "", "product_interest": "steel", "quantity": "10"},
        {"is_inquiry": False},
    ])
    result = process_unread(mailbox, InquiryStore(tmp_path), lambda message: next(classifications))

    assert result.processed == 2
    assert result.inquiries == 1
    assert result.ignored == 1
    assert result.auto_replies_sent == 1
    assert mailbox.replies == ["1"]
    assert mailbox.read == ["1", "2"]
    records = json.loads((tmp_path / "inquiries.json").read_text())
    assert records[0]["email"] == "buyer@example.com"


def test_does_not_reply_twice(tmp_path):
    mailbox = FakeMailbox([{"id": "1", "already_replied": True}])
    result = process_unread(mailbox, InquiryStore(tmp_path), lambda message: {"is_inquiry": True, "company_name": "", "contact_person": "", "email": "", "phone": "", "product_interest": "", "quantity": ""})

    assert result.auto_replies_sent == 0
    assert mailbox.read == ["1"]


def test_processes_ten_sample_emails(tmp_path):
    messages = json.loads((Path(__file__).parent / "sample_emails.json").read_text())
    mailbox = FakeMailbox(messages)
    def classify(message):
        return {"is_inquiry": message["sample_inquiry"], "company_name": "", "contact_person": "", "email": "", "phone": "", "product_interest": "", "quantity": ""}

    result = process_unread(mailbox, InquiryStore(tmp_path), classify)

    assert result.processed == 10
    assert result.inquiries == 5
    assert result.ignored == 5
    assert result.auto_replies_sent == 5


def test_retries_openai_rate_limit(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MIN_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("OPENAI_MAX_RETRIES", "1")
    responses = [
        SimpleNamespace(status_code=429, headers={}, text="busy", json=lambda: {"error": {"code": "rate_limit_exceeded", "message": "slow down"}}),
        SimpleNamespace(status_code=200, headers={}, json=lambda: {"choices": [{"message": {"content": '{"is_inquiry": false}'}}]}, raise_for_status=lambda: None),
    ]
    calls = []

    def request(*args, **kwargs):
        calls.append(kwargs)
        return responses.pop(0)

    result = classify_with_gpt({"subject": "hello", "bodyPreview": "test"}, request)

    assert result["is_inquiry"] is False
    assert len(calls) == 2