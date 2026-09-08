"""Read unread Outlook messages, classify inquiries, and respond once."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any, Callable

import requests
from dotenv import load_dotenv

from send_email import GRAPH_BASE_URL, Settings, get_access_token

AUTO_REPLY = "Thank you for your inquiry. We will get back to you within 24 hours."
INQUIRY_FIELDS = ("company_name", "contact_person", "email", "phone", "product_interest", "quantity")
LOGGER = logging.getLogger("inquiry_processor")
_last_openai_request = 0.0


class OpenAIRateLimitError(RuntimeError):
    """Raised when classification must pause instead of retrying every message."""


def raise_graph_error(response: requests.Response) -> None:
    if response.ok:
        return
    try:
        detail = response.json().get("error", {}).get("message", response.text)
    except ValueError:
        detail = response.text
    raise RuntimeError(f"Microsoft Graph returned HTTP {response.status_code}: {detail}")


@dataclass
class ProcessingResult:
    processed: int = 0
    inquiries: int = 0
    auto_replies_sent: int = 0
    ignored: int = 0
    errors: int = 0


class GraphMailbox:
    """Microsoft Graph operations required by the inbox workflow."""

    def __init__(self, settings: Settings, session: requests.Session | None = None):
        self.settings = settings
        self.session = session or requests.Session()
        self.token = get_access_token(settings)

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def unread_messages(self) -> list[dict[str, Any]]:
        response = self.session.get(
            f"{GRAPH_BASE_URL}/users/{self.settings.sender}/mailFolders/inbox/messages",
            headers=self.headers,
            params={"$filter": "isRead eq false", "$select": "id,subject,from,receivedDateTime,body,bodyPreview,conversationId,internetMessageId", "$top": "100"},
            timeout=30,
        )
        raise_graph_error(response)
        return response.json().get("value", [])

    def mark_read(self, message_id: str) -> None:
        response = self.session.patch(
            f"{GRAPH_BASE_URL}/users/{self.settings.sender}/messages/{message_id}",
            headers=self.headers, json={"isRead": True}, timeout=30,
        )
        raise_graph_error(response)

    def has_replied(self, message: dict[str, Any]) -> bool:
        conversation_id = message.get("conversationId")
        if not conversation_id:
            return False
        response = self.session.get(
            f"{GRAPH_BASE_URL}/users/{self.settings.sender}/mailFolders/sentitems/messages",
            headers=self.headers,
            params={"$filter": f"conversationId eq '{conversation_id}'", "$top": "1", "$select": "id"},
            timeout=30,
        )
        raise_graph_error(response)
        return bool(response.json().get("value"))

    def reply(self, message_id: str, body: str = AUTO_REPLY) -> None:
        response = self.session.post(
            f"{GRAPH_BASE_URL}/users/{self.settings.sender}/messages/{message_id}/reply",
            headers=self.headers, json={"comment": body}, timeout=30,
        )
        raise_graph_error(response)


class InquiryStore:
    """SQLite audit store plus JSON and Excel exports."""

    def __init__(self, data_dir: str | Path = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.database = self.data_dir / "inquiries.sqlite3"
        with sqlite3.connect(self.database) as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS messages (message_id TEXT PRIMARY KEY, status TEXT NOT NULL, processed_at TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS inquiries (message_id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL)")

    def already_processed(self, message_id: str) -> bool:
        with sqlite3.connect(self.database) as connection:
            return connection.execute("SELECT 1 FROM messages WHERE message_id = ?", (message_id,)).fetchone() is not None

    def record(self, message_id: str, status: str, inquiry: dict[str, Any] | None = None) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.database) as connection:
            connection.execute("INSERT OR REPLACE INTO messages VALUES (?, ?, ?)", (message_id, status, timestamp))
            if inquiry is not None:
                connection.execute("INSERT OR REPLACE INTO inquiries VALUES (?, ?, ?)", (message_id, json.dumps(inquiry), timestamp))
        self.export()

    def export(self) -> None:
        with sqlite3.connect(self.database) as connection:
            rows = connection.execute("SELECT message_id, payload, created_at FROM inquiries ORDER BY created_at").fetchall()
        records = [{**json.loads(payload), "message_id": message_id, "timestamp": timestamp} for message_id, payload, timestamp in rows]
        (self.data_dir / "inquiries.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
        try:
            import openpyxl
            workbook = openpyxl.Workbook()
            sheet = workbook.active
            sheet.append([*INQUIRY_FIELDS, "message_id", "timestamp"])
            for record in records:
                sheet.append([record.get(field, "") for field in (*INQUIRY_FIELDS, "message_id", "timestamp")])
            workbook.save(self.data_dir / "inquiries.xlsx")
        except ImportError:
            LOGGER.warning("openpyxl is unavailable; JSON export is still available")


def message_text(message: dict[str, Any]) -> str:
    body = message.get("body", {})
    content = body.get("content") if isinstance(body, dict) else None
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", content or message.get("bodyPreview", "")))).strip()


def _openai_error(response: requests.Response) -> tuple[str, str]:
    try:
        error = response.json().get("error", {})
        return str(error.get("code", "")), str(error.get("message", response.text))
    except ValueError:
        return "", response.text


def classify_with_gpt(message: dict[str, Any], request: Callable[..., requests.Response] = requests.post) -> dict[str, Any]:
    """Ask a configured GPT-compatible endpoint for strict JSON classification."""
    api_key = os.getenv("OPENAI_API_KEY")
    endpoint = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/chat/completions")
    model = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for inquiry classification")
    prompt = (
        "Classify this email as an inquiry only when it concerns products, prices, orders, services, quotes, availability, or partnerships. "
        "Exclude promotions, spam, newsletters, auto-replies, and internal emails. Return JSON only with keys is_inquiry (boolean), "
        "company_name, contact_person, email, phone, product_interest, quantity. Use empty strings for unknown fields.\n\n"
        f"Subject: {message.get('subject', '')}\nFrom: {message.get('from', {}).get('emailAddress', {}).get('address', '')}\nBody: {message_text(message)}"
    )
    global _last_openai_request
    min_interval = float(os.getenv("OPENAI_MIN_INTERVAL_SECONDS", "1"))
    max_retries = int(os.getenv("OPENAI_MAX_RETRIES", "3"))
    max_backoff = float(os.getenv("OPENAI_MAX_BACKOFF_SECONDS", "30"))
    payload = {"model": model, "temperature": 0, "response_format": {"type": "json_object"}, "messages": [{"role": "user", "content": prompt}]}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    for attempt in range(max_retries + 1):
        wait = min_interval - (time.monotonic() - _last_openai_request)
        if wait > 0:
            time.sleep(wait)
        response = request(endpoint, headers=headers, json=payload, timeout=60)
        _last_openai_request = time.monotonic()
        if response.status_code != 429:
            response.raise_for_status()
            break

        error_code, detail = _openai_error(response)
        if error_code in {"insufficient_quota", "billing_hard_limit_reached"}:
            raise OpenAIRateLimitError(f"OpenAI quota is unavailable: {detail}")
        if attempt == max_retries:
            raise OpenAIRateLimitError(f"OpenAI rate limit persisted after {max_retries} retries: {detail}")
        retry_after = response.headers.get("Retry-After")
        try:
            backoff = float(retry_after) if retry_after else 2 ** attempt
        except ValueError:
            backoff = 2 ** attempt
        time.sleep(min(max_backoff, max(0, backoff)))
        LOGGER.warning("OpenAI rate limit; retry %s/%s in %.1f seconds", attempt + 1, max_retries, min(max_backoff, max(0, backoff)))

    result = json.loads(response.json()["choices"][0]["message"]["content"])
    return {"is_inquiry": bool(result.get("is_inquiry")), **{field: str(result.get(field, "") or "") for field in INQUIRY_FIELDS}}


def process_unread(mailbox: GraphMailbox, store: InquiryStore, classifier: Callable[[dict[str, Any]], dict[str, Any]] = classify_with_gpt) -> ProcessingResult:
    result = ProcessingResult()
    for message in mailbox.unread_messages():
        message_id = message.get("id")
        if not message_id or store.already_processed(message_id):
            continue
        result.processed += 1
        try:
            classification = classifier(message)
            if classification["is_inquiry"]:
                result.inquiries += 1
                classification["email"] = classification["email"] or message.get("from", {}).get("emailAddress", {}).get("address", "")
                if not mailbox.has_replied(message):
                    mailbox.reply(message_id)
                    result.auto_replies_sent += 1
                else:
                    LOGGER.info("Skipping duplicate reply for %s", message_id)
                store.record(message_id, "inquiry", classification)
            else:
                result.ignored += 1
                store.record(message_id, "ignored")
            mailbox.mark_read(message_id)
        except OpenAIRateLimitError as error:
            result.errors += 1
            LOGGER.error("Stopping inbox processing because classification is rate limited: %s", error)
            break
        except Exception:
            result.errors += 1
            LOGGER.exception("Failed to process message %s; continuing", message_id)
    LOGGER.info("Processed: %s, Inquiries: %s, Auto-replies sent: %s", result.processed, result.inquiries, result.auto_replies_sent)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Process unread Outlook inquiries")
    parser.add_argument("--data-dir", default=os.getenv("INQUIRY_DATA_DIR", "data"))
    args = parser.parse_args()
    load_dotenv()
    logging.basicConfig(filename="inquiry_processor.log", level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = process_unread(GraphMailbox(Settings.from_environment()), InquiryStore(args.data_dir))
    print(f"Processed: {result.processed}, Inquiries: {result.inquiries}, Auto-replies sent: {result.auto_replies_sent}")


if __name__ == "__main__":
    main()