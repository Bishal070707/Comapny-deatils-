"""Read unread Outlook messages, classify inquiries, and respond once with strict rules."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sqlite3
import joblib
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any, Callable

import requests
from dotenv import load_dotenv
from huggingface_hub import hf_hub_download

from send_email import GRAPH_BASE_URL, Settings, get_access_token

AUTO_REPLY = "Thank you for your inquiry. We will get back to you within 24 hours."
INQUIRY_FIELDS = ("company_name", "contact_person", "email", "phone", "product_interest", "quantity")
LOGGER = logging.getLogger("inquiry_processor")

# Global variable for model
_spam_model = None

# ============ COMPLETE PRODUCT CATALOG FROM YOUR IMAGE ============
PRODUCT_CATALOG = {
    # Angles
    "Angle": ["angle", "ms angle", "angle 35x35", "angle 40x40", "angle 50x50"],
    
    # Beams
    "Beam": ["beam", "ms beam", "i-beam", "h-beam", "ibeam"],
    
    # Channels
    "Channel": ["channel", "ms channel", "isc", "ms ismc", "channel 100x50", "ismc"],
    
    # Plates
    "Plate": ["plate", "chequered plate", "ms plate", "checkered plate", "chequer plate"],
    
    # Sheets
    "Sheet": ["sheet", "cr sheet", "gi sheet", "profile sheet", "sheets", "crca", "galvanized"],
    
    # TMT Bars
    "TMT Bar": ["tmt", "tmt bar", "sariya", "rebar", "tmt steel"],
    
    # Pipes & Tubes
    "Pipe": ["pipe", "tube", "ms pipe", "gi pipe", "square hollow", "shs", "rectangular hollow"],
    
    # Flats
    "Flat": ["flat", "ms flat", "flat bar", "gi strip"],
    
    # Rounds
    "Round": ["round", "ms round", "s.s.round", "ss round", "solid round"],
    
    # Squares
    "Square": ["square", "ms square", "square", "square bar"],
    
    # Fasteners
    "Nut & Bolt": ["nut", "bolt", "nut & bolt", "fastener", "fasteners"],
    "Hardware": ["hardware", "fitting", "pipe fitting", "pipe fittings"],
    
    # Safety Equipment
    "Safety": ["safety", "goggles", "shoe", "cover", "safety goggles", "safety shoes"],
    
    # Wires
    "Wire": ["wire", "gi wire", "ms wire", "galvanized wire"],
    
    # Rods
    "Rod": ["rod", "ms rod", "round rod", "steel rod"],
    
    # Rails
    "Rail": ["rail", "rails", "train rail"],
    
    # Structure Steel
    "Structure Steel": ["structure steel", "structural steel", "steel structure"],
    
    # Gun Metal
    "Gun Metal": ["gun metal", "gunmetal"],
    
    # Zinc
    "Zinc": ["zinc", "zinc metal"],
}

# Product patterns for detection (from your HSN list)
# Product patterns for detection (from your HSN list)
PRODUCT_PATTERNS = [
    # General steel products
    r"ms\s+(?:angle|channel|beam|plate|flat|square|round|pipe|tube|sheet|strip)",
    r"gi\s+(?:sheet|pipe|wire|strip)",
    r"ss\s+(?:flat|round|sheet|pipe)",
    r"cr\s+sheet",
    
    # Specific products
    r"angle\s+\d{1,3}x\d{1,3}(?:x\d{1,3})?",
    r"channel\s+\d{1,3}x\d{1,3}",
    r"beam\s+\d{1,3}x\d{1,3}",
    r"ismc\s+\d{1,3}x\d{1,3}",
    r"shs\s*\d{1,3}x\d{1,3}x\d{1,3}",
    r"tmt\s+bar",
    r"chequered\s+plate",
    r"profile\s+sheet",
    r"gi\s+(?:wire|strip)",
    r"ms\s+rod",
    r"square\s+hollow",
    
    # Dimensions and quantities - UPDATED with more units
    r"\d+\s*mm",  # Dimensions
    r"\d+\.?\d*\s*(?:mt|t|ton|tons|kg|kilogram|gms|piece|pcs|nos|qty|meter|m|feet|ft)",  # ALL quantity units
    r"\d+\.?\d*\s*MT",  # MT (case insensitive)
    r"\d+\.?\d*\s*T\b",  # T (Tons - standalone)
    r"\d+\.?\d*\s*KG",  # KG (case insensitive)
    r"\d+\.?\d*\s*Kg",  # Kg
    r"\d+\.?\d*\s*Gms",  # Grams
    r"\d+\.?\d*\s*Nos",  # Numbers/Count
    r"\d+\.?\d*\s*Pcs",  # Pieces
    r"\d+\.?\d*\s*Qty",  # Quantity
    r"\d+\s*x\s*\d+\s*mm",  # Dimensions like 100x50mm
    
    # HSN codes (optional)
    r"hsn\s*\d{4,8}",
]

# =========================================================

# ============ STRICT INQUIRY CLASSIFICATION ============
# These are required for an email to be considered a genuine inquiry
REQUIRED_INQUIRY_PATTERNS = [
    r"(?:price|quote|rate|cost|best)\s+(?:of|for|on|quotation|offer)",  # Asking for price/quote
    r"(?:need|want|require|looking for|interested in)\s+\d+",  # Expressing need with quantity
    r"please\s+(?:send|provide|share|quote|give)\s+(?:me|us|your)",  # Request for info
    r"(?:order|purchase|buy)\s+(?:for|of)",  # Purchase intent
    r"(?:mt|kg|ton|piece|nos|qty)\s+(?:of|for)",  # Units with products
    r"(?:project|construction|building|site)\s+(?:name|location|for)",  # Project mention
    r"send\s+(?:us|me)\s+your\s+(?:best|latest|current)\s+(?:price|rate|quote)",  # Send price
    r"what\s+is\s+(?:your|the)\s+(?:price|rate|cost)\s+(?:of|for)",  # What is price
    r"i\s+(?:want|need)\s+to\s+(?:buy|order|purchase)",  # Want to buy
    r"कृपया\s+(?:भेजें|बताएं|कीमत|रेट)",  # Hindi: Please send/tell price
    r"जरूरत\s+(?:है|चाहिए)",  # Hindi: Need/require
]

# Patterns that indicate it's NOT a genuine inquiry (auto-reject)
NON_INQUIRY_PATTERNS = [
    r"(?:invoice|bill|receipt)\s+(?:#|no|number)",  # Invoice notifications
    r"(?:delivery|shipment|tracking)\s+(?:#|no)",  # Delivery notifications
    r"your\s+(?:order|account|profile|payment)",  # Automated notifications
    r"(?:newsletter|subscription|unsubscribe|digest)",  # Newsletters
    r"(?:payment|credit|debit)\s+(?:card|account)",  # Payment notifications
    r"(?:meeting|calendar|invitation)\s+(?:invite|request|schedule)",  # Meeting invites
    r"covid(?:-19)?",  # COVID notifications
    r"(?:gift|card|coupon|discount)\s+(?:offer|code)",  # Promotional
    r"please\s+(?:rate|review|feedback|complete survey)",  # Feedback requests
    r"your\s+(?:statement|report|summary)",  # Reports/statements
    r"(?:job|employment|position|career|hiring)",  # Job-related
    r"(?:internship|training|fresher)",  # Internship/training
    r"(?:marketing|advertisement|promotion|campaign)",  # Marketing
    r"(?:donation|charity|fundraising)",  # Donations
]

# Spam keywords (auto-reject)
SPAM_KEYWORDS = [
    "congratulations", "winner", "prize", "lottery", "million",
    "dollar", "cash", "free", "urgent", "click here", "subscribe",
    "unsubscribe", "newsletter", "marketing", "promotion", "advertisement",
    "viagra", "porn", "sex", "dating", "casino", "gambling", "betting",
    "win", "claim", "reward", "bonus", "porn", "adult", "xxx"
]
# =========================================================

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
            params={
                "$filter": "isRead eq false",
                "$select": "id,subject,from,receivedDateTime,body,bodyPreview,conversationId,internetMessageId",
                "$top": "100"
            },
            timeout=30,
        )
        raise_graph_error(response)
        return response.json().get("value", [])

    def mark_read(self, message_id: str) -> None:
        response = self.session.patch(
            f"{GRAPH_BASE_URL}/users/{self.settings.sender}/messages/{message_id}",
            headers=self.headers,
            json={"isRead": True},
            timeout=30,
        )
        raise_graph_error(response)

    def has_replied(self, message: dict[str, Any]) -> bool:
        conversation_id = message.get("conversationId")
        if not conversation_id:
            return False
        response = self.session.get(
            f"{GRAPH_BASE_URL}/users/{self.settings.sender}/mailFolders/sentitems/messages",
            headers=self.headers,
            params={
                "$filter": f"conversationId eq '{conversation_id}'",
                "$top": "1",
                "$select": "id"
            },
            timeout=30,
        )
        raise_graph_error(response)
        return bool(response.json().get("value"))

    def reply(self, message_id: str, body: str = AUTO_REPLY) -> None:
        response = self.session.post(
            f"{GRAPH_BASE_URL}/users/{self.settings.sender}/messages/{message_id}/reply",
            headers=self.headers,
            json={"comment": body},
            timeout=30,
        )
        raise_graph_error(response)


class InquiryStore:
    """SQLite audit store plus JSON and Excel exports."""

    def __init__(self, data_dir: str | Path = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.database = self.data_dir / "inquiries.sqlite3"
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS messages (message_id TEXT PRIMARY KEY, status TEXT NOT NULL, processed_at TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS inquiries (message_id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL)"
            )

    def already_processed(self, message_id: str) -> bool:
        with sqlite3.connect(self.database) as connection:
            return connection.execute(
                "SELECT 1 FROM messages WHERE message_id = ?", (message_id,)
            ).fetchone() is not None

    def record(self, message_id: str, status: str, inquiry: dict[str, Any] | None = None) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO messages VALUES (?, ?, ?)",
                (message_id, status, timestamp)
            )
            if inquiry is not None:
                connection.execute(
                    "INSERT OR REPLACE INTO inquiries VALUES (?, ?, ?)",
                    (message_id, json.dumps(inquiry), timestamp)
                )
        self.export()

    def export(self) -> None:
        with sqlite3.connect(self.database) as connection:
            rows = connection.execute(
                "SELECT message_id, payload, created_at FROM inquiries ORDER BY created_at"
            ).fetchall()
        
        records = [
            {**json.loads(payload), "message_id": message_id, "timestamp": timestamp}
            for message_id, payload, timestamp in rows
        ]
        
        (self.data_dir / "inquiries.json").write_text(
            json.dumps(records, indent=2), encoding="utf-8"
        )
        
        try:
            import openpyxl
            workbook = openpyxl.Workbook()
            sheet = workbook.active
            sheet.append([*INQUIRY_FIELDS, "message_id", "timestamp"])
            for record in records:
                sheet.append([
                    record.get(field, "") for field in (*INQUIRY_FIELDS, "message_id", "timestamp")
                ])
            workbook.save(self.data_dir / "inquiries.xlsx")
        except ImportError:
            LOGGER.warning("openpyxl is unavailable; JSON export is still available")


def message_text(message: dict[str, Any]) -> str:
    """Extract plain text from email body."""
    body = message.get("body", {})
    content = body.get("content") if isinstance(body, dict) else None
    # Remove HTML tags and normalize whitespace
    text = re.sub(r"<[^>]+>", " ", content or message.get("bodyPreview", ""))
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_field(text: str, pattern: str) -> str | None:
    """Extract field using regex pattern."""
    match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip() if match else None


def detect_products(text: str) -> list[str]:
    """Detect product types from email text based on catalog."""
    text_lower = text.lower()
    found_products = []
    
    # Check each product category
    for category, keywords in PRODUCT_CATALOG.items():
        for keyword in keywords:
            if keyword in text_lower:
                found_products.append(category)
                break
    
    # Check for dimension patterns (e.g., 40mm, 100x50mm)
    if re.search(r"\d+\s*mm", text_lower):
        if "Angle" not in found_products and "Beam" not in found_products:
            found_products.append("Steel Product")
    
    # Check for MS/GI/SS patterns
    if re.search(r"\b(ms|gi|ss|cr)\s+[a-z]+", text_lower):
        found_products.append("Steel Product")
    
    return list(set(found_products))  # Remove duplicates


def load_classifier():
    """Lazy load the TF-IDF + Logistic Regression model from Hugging Face."""
    global _spam_model
    
    if _spam_model is None:
        LOGGER.info("Loading spam detection model (first time may take a moment)...")
        try:
            model_path = hf_hub_download("Anurag43/enron-spam-detector", "spam_model.joblib")
            _spam_model = joblib.load(model_path)
            LOGGER.info("Model loaded successfully")
        except Exception as e:
            LOGGER.warning(f"Failed to load spam model: {e}. Will use rule-based detection only.")
            _spam_model = None
    
    return _spam_model


def is_genuine_inquiry(full_text: str) -> tuple[bool, list[str]]:
    """
    Check if this is a genuine business inquiry using strict rules.
    Returns: (is_inquiry, reasons)
    """
    reasons = []
    
    # ===== STEP 1: Check for spam =====
    for keyword in SPAM_KEYWORDS:
        if keyword in full_text:
            return False, [f"Contains spam keyword: {keyword}"]
    
    # ===== STEP 2: Check for non-inquiry patterns (auto-reject) =====
    for pattern in NON_INQUIRY_PATTERNS:
        if re.search(pattern, full_text, re.IGNORECASE):
            return False, [f"Non-inquiry pattern: {pattern}"]
    
    # ===== STEP 3: Check for product mentions =====
    product_matches = []
    for pattern in PRODUCT_PATTERNS:
        if re.search(pattern, full_text, re.IGNORECASE):
            product_matches.append(pattern)
    
    detected_products = detect_products(full_text)
    
    # ===== STEP 4: Check for quantities - UPDATED with more units =====
    has_quantity = bool(re.search(
        r"\d+\.?\d*\s*(?:mt|t|ton|tons|kg|kilogram|gms|piece|pcs|nos|qty|mm|meter|m|feet|ft)", 
        full_text, 
        re.IGNORECASE
    ))
    
    # ===== STEP 5: Check for inquiry language =====
    has_inquiry_pattern = False
    for pattern in REQUIRED_INQUIRY_PATTERNS:
        if re.search(pattern, full_text, re.IGNORECASE):
            has_inquiry_pattern = True
            reasons.append(f"Found inquiry pattern: {pattern[:30]}...")
            break
    
    # ===== DECISION LOGIC =====
    
    # Rule 1: If it has both product AND inquiry pattern, it's an inquiry
    if product_matches and has_inquiry_pattern:
        reasons.append(f"Found {len(product_matches)} product patterns + inquiry language")
        return True, reasons
    
    # Rule 2: If it has multiple products + quantities, it's an inquiry (even without inquiry language)
    if len(product_matches) >= 2 and has_quantity:
        reasons.append(f"Multiple products ({len(product_matches)}) with quantities")
        return True, reasons
    
    # Rule 3: If it has products + specific project mention, it's an inquiry
    if product_matches and re.search(r"(?:project|site|construction|building)", full_text, re.IGNORECASE):
        reasons.append("Product + project mention")
        return True, reasons
    
    # Rule 4: If it has inquiry pattern but no products, it's PROBABLY an inquiry (but caution)
    if has_inquiry_pattern and not product_matches:
        # Check if it's asking for rate list or catalog
        if re.search(r"(?:rate list|price list|catalog|brochure)", full_text, re.IGNORECASE):
            reasons.append("Asking for rate list/catalog")
            return True, reasons
    
    # Rule 5: If it has products but no inquiry pattern and no quantity, it's NOT an inquiry
    if product_matches and not has_inquiry_pattern and not has_quantity:
        return False, ["Products found but no inquiry language or quantities"]
    
    # Default: If no conditions met, it's NOT an inquiry
    if not reasons:
        reasons.append("No inquiry indicators found")
    
    return False, reasons

def classify_inquiry(message: dict[str, Any]) -> dict[str, Any]:
    """
    Hybrid classifier: Uses strict rules to identify genuine inquiries.
    """
    from_address = message.get("from", {}).get("emailAddress", {}).get("address", "")
    subject = message.get("subject", "")
    body = message_text(message)
    full_text = f"{subject} {body}".lower()
    
    # ========== STRICT INQUIRY DETECTION ==========
    is_inquiry, reasons = is_genuine_inquiry(full_text)
    
    # Detect products
    detected_products = detect_products(full_text)
    
    # Extract fields
    company_name = extract_field(body, r"(?:Company|Organization|Business|Firm|Project)[:\s]+(.+?)(?:\n|$)")
    contact_person = extract_field(body, r"(?:Contact|Name|Person|Attn|Sir|Madam)[:\s]+(.+?)(?:\n|$)")
    email = extract_field(body, r"(?:Email|E-mail)[:\s]+(.+?)(?:\n|$)")
    phone = extract_field(body, r"(?:Phone|Tel|Mobile)[:\s]+(.+?)(?:\n|$)")
    product_interest = ", ".join(detected_products) if detected_products else ""
    quantity = extract_field(body, r"(?:Quantity|Qty|Total)[:\s]+(.+?)(?:\n|$)")
    
    # If email not found in body, use from address
    if not email:
        email = from_address
    
    # ===== TRY MULTIPLE QUANTITY PATTERNS (UPDATED) =====
    if not quantity:
        # Try MT (Metric Tons)
        qty_match = re.search(r"=\s*(\d+\.?\d*)\s*MT", full_text, re.IGNORECASE)
        if qty_match:
            quantity = qty_match.group(1) + " MT"
    
    if not quantity:
        # Try T (Tons)
        qty_match = re.search(r"=\s*(\d+\.?\d*)\s*T\b", full_text, re.IGNORECASE)
        if qty_match:
            quantity = qty_match.group(1) + " T"
    
    if not quantity:
        # Try KG (Kilograms)
        qty_match = re.search(r"=\s*(\d+\.?\d*)\s*KG", full_text, re.IGNORECASE)
        if qty_match:
            quantity = qty_match.group(1) + " KG"
    
    if not quantity:
        # Try any number + unit pattern
        qty_match = re.search(r"(\d+\.?\d*)\s*(?:MT|T|TON|KG|GMS|PCS|NOS)", full_text, re.IGNORECASE)
        if qty_match:
            unit = qty_match.group(2).upper() if qty_match.lastindex and qty_match.lastindex >= 2 else "UNITS"
            quantity = qty_match.group(1) + " " + unit
    
    # If still no quantity, check for any number + mt/kg/ton
    if not quantity:
        qty_match = re.search(r"(\d+\.?\d*)\s*(?:MT|ton|kg|T)", full_text, re.IGNORECASE)
        if qty_match:
            unit = qty_match.group(2).upper() if qty_match.lastindex and qty_match.lastindex >= 2 else "UNITS"
            quantity = qty_match.group(1) + " " + unit
    
    # Log the decision
    LOGGER.info(f"Email from {from_address}: Is Inquiry={is_inquiry}, Reasons={reasons[:3]}")
    
    return {
        "is_inquiry": is_inquiry,
        "company_name": company_name or "",
        "contact_person": contact_person or "",
        "email": email or "",
        "phone": phone or "",
        "product_interest": product_interest or "",
        "quantity": quantity or "",
        "detected_products": detected_products,
        "reasons": reasons,
        "is_spam": False
    }

def process_unread(
    mailbox: GraphMailbox,
    store: InquiryStore,
    classifier: Callable[[dict[str, Any]], dict[str, Any]] = classify_inquiry
) -> ProcessingResult:
    """
    Process all unread messages using the provided classifier.
    """
    result = ProcessingResult()
    
    messages = mailbox.unread_messages()
    LOGGER.info(f"Found {len(messages)} unread messages")
    
    for message in messages:
        message_id = message.get("id")
        if not message_id or store.already_processed(message_id):
            continue
            
        result.processed += 1
        
        try:
            # Classify the message
            classification = classifier(message)
            
            # ONLY send auto-reply if it's a genuine inquiry
            if classification.get("is_inquiry", False):
                # It's a genuine inquiry
                result.inquiries += 1
                
                # Ensure email field is populated
                if not classification.get("email"):
                    classification["email"] = message.get("from", {}).get("emailAddress", {}).get("address", "")
                
                # Send auto-reply ONLY if not already replied
                if not mailbox.has_replied(message):
                    mailbox.reply(message_id)
                    result.auto_replies_sent += 1
                    LOGGER.info(f"✅ Sent auto-reply to genuine inquiry from {classification['email']}")
                else:
                    LOGGER.info(f"Skipping duplicate reply for {message_id}")
                
                # Store inquiry details
                store.record(message_id, "inquiry", classification)
                
            else:
                # Not a genuine inquiry - DO NOT send auto-reply
                result.ignored += 1
                store.record(message_id, "ignored")
                LOGGER.debug(f"Skipped non-inquiry from {message.get('from', {}).get('emailAddress', {}).get('address', '')}")
            
            # Mark as read
            mailbox.mark_read(message_id)
            
        except Exception as e:
            result.errors += 1
            LOGGER.exception(f"Failed to process message {message_id}: {e}")
    
    LOGGER.info(
        f"Processed: {result.processed}, "
        f"Inquiries: {result.inquiries}, "
        f"Auto-replies sent: {result.auto_replies_sent}, "
        f"Ignored: {result.ignored}, "
        f"Errors: {result.errors}"
    )
    
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Process unread Outlook inquiries")
    parser.add_argument("--data-dir", default=os.getenv("INQUIRY_DATA_DIR", "data"))
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()
    
    # Load environment variables
    load_dotenv()
    
    # Setup logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        filename="inquiry_processor.log",
        level=log_level,
        format="%(asctime)s %(levelname)s %(message)s"
    )
    
    # Also log to console
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    logging.getLogger().addHandler(console_handler)
    
    try:
        # Load model if available
        load_classifier()
        
        # Initialize components
        settings = Settings.from_environment()
        mailbox = GraphMailbox(settings)
        store = InquiryStore(args.data_dir)
        
        # Process messages
        result = process_unread(mailbox, store)
        
        print(f"\n=== Summary ===")
        print(f"Processed: {result.processed}")
        print(f"Genuine Inquiries: {result.inquiries}")
        print(f"Auto-replies sent: {result.auto_replies_sent}")
        print(f"Ignored: {result.ignored}")
        print(f"Errors: {result.errors}")
        print(f"\nInquiry data saved to: {args.data_dir}/inquiries.json")
        print(f"Logs saved to: inquiry_processor.log")
        
    except Exception as e:
        LOGGER.error(f"Fatal error: {e}")
        print(f"Error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
