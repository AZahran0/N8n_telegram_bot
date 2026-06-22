"""
tools.py — Equivalent to all tool nodes in n8n:
  - create_new_order        (Google Sheets Tool)
  - modify_existing_order   (Google Sheets Tool)
  - cancel_order            (Google Sheets Tool)
  - search_menu             (Supabase Vector Store Tool)
  - faq                     (Supabase Vector Store Tool)
  - get_order_history       (Google Sheets Tool)
  - issue_compensation      (Google Sheets Tool)
  - escalate_to_human       (stub — implement your own notification)

SECURITY FIX INCLUDED:
  modify_existing_order and cancel_order now do a read-then-verify
  before writing, preventing fake order ID abuse.
"""

import logging
import uuid
from datetime import datetime
from typing import Any

import gspread
from google.oauth2.service_account import Credentials
from openai import OpenAI
from supabase import create_client

from config import (
    GOOGLE_CREDENTIALS_FILE, ORDERS_SHEET_ID, ORDERS_SHEET_NAME,
    SUPABASE_URL, SUPABASE_API_KEY, OPENAI_API_KEY
)

logger = logging.getLogger(__name__)

# ── Clients (lazy singletons) ──────────────────────────────

_sheets_client = None
_supabase_client = None
_openai_client = None


def _get_sheet():
    global _sheets_client
    if _sheets_client is None:
        scopes = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_FILE, scopes=scopes)
        gc = gspread.authorize(creds)
        _sheets_client = gc.open_by_key(ORDERS_SHEET_ID).worksheet(ORDERS_SHEET_NAME)
    return _sheets_client


def _get_supabase():
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_API_KEY)
    return _supabase_client


def _get_openai():
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
    return _openai_client


# ── Helper: look up order by ID ────────────────────────────

def _find_order_row(order_id: str) -> dict | None:
    """
    SECURITY: Read-then-verify before any write operation.
    Returns the row dict if found, None otherwise.
    """
    sheet = _get_sheet()
    records = sheet.get_all_records()
    for i, row in enumerate(records, start=2):  # row 1 is header
        if str(row.get("ID", "")).strip() == str(order_id).strip():
            return {"row_index": i, "data": row}
    return None


# ── Tool: create_new_order ─────────────────────────────────

def create_new_order(items: list[str], name: str, phone: str) -> str:
    """
    Equivalent to the create_new_order Google Sheets Tool node.
    Appends a new row to the Orders sheet.
    """
    try:
        sheet = _get_sheet()
        order_id = str(uuid.uuid4())[:8].upper()
        now = datetime.now().isoformat()
        items_str = ", ".join(items)

        sheet.append_row([
            now,          # Time
            items_str,    # Item
            "",           # Price (agent fills this from menu)
            order_id,     # ID
            name,         # Name
            str(phone),   # Phone Number
            "In Kitchen", # Status
        ])

        logger.info(f"Order created: {order_id} for {name}")
        return f"Order placed successfully! Your order ID is **{order_id}**. Items: {items_str}."

    except Exception as e:
        logger.error(f"create_new_order error: {e}")
        return "Sorry, I couldn't place your order right now. Please try again."


# ── Tool: modify_existing_order ────────────────────────────

def modify_existing_order(order_id: str, action: str, item_name: str) -> str:
    """
    Equivalent to modify_existing_order node — but with SECURITY FIX:
    Verifies order exists and is still modifiable before writing.
    """
    try:
        existing = _find_order_row(order_id)

        if not existing:
            return f"❌ Order ID '{order_id}' was not found. Please double-check your order ID."

        status = str(existing["data"].get("Status", "")).strip()
        if status in ("Shipped", "Delivered"):
            return f"Sorry, order {order_id} has already been {status.lower()} and can no longer be modified."

        # Get current items and modify
        sheet = _get_sheet()
        current_items = str(existing["data"].get("Item ", ""))
        items_list = [i.strip() for i in current_items.split(",") if i.strip()]

        if action == "add":
            items_list.append(item_name)
            new_items = ", ".join(items_list)
        elif action == "remove":
            items_list = [i for i in items_list if i.lower() != item_name.lower()]
            new_items = ", ".join(items_list)
        else:
            return f"Unknown action '{action}'. Use 'add' or 'remove'."

        # Update the cell — column B (index 2) is "Item"
        sheet.update_cell(existing["row_index"], 2, new_items)
        logger.info(f"Order {order_id} modified: {action} {item_name}")
        return f"✅ Order {order_id} updated. New items: {new_items}."

    except Exception as e:
        logger.error(f"modify_existing_order error: {e}")
        return "Sorry, I couldn't modify the order right now. Please try again."


# ── Tool: cancel_order ─────────────────────────────────────

def cancel_order(order_id: str, reason: str = "") -> str:
    """
    Equivalent to cancel_order node — with SECURITY FIX:
    Verifies order exists and is cancellable before updating status.
    """
    try:
        existing = _find_order_row(order_id)

        if not existing:
            return f"❌ Order ID '{order_id}' was not found. Please double-check your order ID."

        status = str(existing["data"].get("Status", "")).strip()
        if status in ("Shipped", "Delivered"):
            return f"Sorry, order {order_id} has already been {status.lower()} and cannot be cancelled. Please contact support."

        if status == "Cancelled":
            return f"Order {order_id} is already cancelled."

        # Update status to Cancelled — column G (index 7) is "Status"
        sheet = _get_sheet()
        sheet.update_cell(existing["row_index"], 7, "Cancelled")
        logger.info(f"Order {order_id} cancelled. Reason: {reason}")
        return f"✅ Order {order_id} has been cancelled. If you were charged, a refund will be processed within 3-5 business days."

    except Exception as e:
        logger.error(f"cancel_order error: {e}")
        return "Sorry, I couldn't cancel the order right now. Please try again."


# ── Tool: search_menu (RAG) ────────────────────────────────

def search_menu(query: str) -> str:
    """
    Equivalent to the search_menu Supabase Vector Store Tool node.
    Embeds the query with OpenAI, then does similarity search in Supabase.
    """
    try:
        openai = _get_openai()
        supabase = _get_supabase()

        # Generate embedding for the query
        embedding_response = openai.embeddings.create(
            input=query,
            model="text-embedding-3-small"
        )
        query_embedding = embedding_response.data[0].embedding

        # Call the Supabase match function (same as n8n's match_menu)
        result = supabase.rpc("match_menu", {
            "query_embedding": query_embedding,
            "match_count": 5,
        }).execute()

        if not result.data:
            return "I couldn't find any menu items matching that query."

        items = []
        for row in result.data:
            content = row.get("content", row.get("document", str(row)))
            items.append(content)

        return "\n\n".join(items)

    except Exception as e:
        logger.error(f"search_menu error: {e}")
        return "Sorry, I couldn't search the menu right now."


# ── Tool: faq (RAG) ───────────────────────────────────────

def faq(query: str) -> str:
    """
    Equivalent to the FAQ Supabase Vector Store Tool node.
    """
    try:
        openai = _get_openai()
        supabase = _get_supabase()

        embedding_response = openai.embeddings.create(
            input=query,
            model="text-embedding-3-small"
        )
        query_embedding = embedding_response.data[0].embedding

        result = supabase.rpc("match_faq", {
            "query_embedding": query_embedding,
            "match_count": 3,
        }).execute()

        if not result.data:
            return "I couldn't find an answer to that question in our FAQ."

        answers = []
        for row in result.data:
            content = row.get("content", row.get("document", str(row)))
            answers.append(content)

        return "\n\n".join(answers)

    except Exception as e:
        logger.error(f"faq error: {e}")
        return "Sorry, I couldn't search the FAQ right now."


# ── Tool: get_order_history ────────────────────────────────

def get_order_history(order_id: str) -> str:
    """Retrieves order details from the sheet for complaint investigation."""
    try:
        existing = _find_order_row(order_id)
        if not existing:
            return f"No order found with ID '{order_id}'."

        data = existing["data"]
        return (
            f"Order {order_id} details:\n"
            f"- Items: {data.get('Item ', 'N/A')}\n"
            f"- Status: {data.get('Status', 'N/A')}\n"
            f"- Time placed: {data.get('Time ', 'N/A')}\n"
            f"- Customer: {data.get('Name', 'N/A')}"
        )
    except Exception as e:
        logger.error(f"get_order_history error: {e}")
        return "Sorry, I couldn't retrieve the order history right now."


# ── Tool: issue_compensation ───────────────────────────────

def issue_compensation(order_id: str, type: str, amount: float) -> str:
    """
    Issues a refund or voucher.
    Hard cap of $15 enforced in code — cannot be overridden by prompt.
    """
    MAX_COMPENSATION = 15.0

    if amount > MAX_COMPENSATION:
        logger.warning(f"Compensation amount ${amount} exceeds limit. Capping at ${MAX_COMPENSATION}.")
        amount = MAX_COMPENSATION

    existing = _find_order_row(order_id)
    if not existing:
        return f"❌ Order ID '{order_id}' not found. Cannot issue compensation."

    # In production: call your payment/voucher API here
    logger.info(f"Compensation issued: {type} of ${amount} for order {order_id}")
    return (
        f"✅ A {type} of ${amount:.2f} has been issued for order {order_id}. "
        f"{'Your refund will appear in 3-5 business days.' if type == 'refund' else 'Your voucher code will be sent shortly.'}"
    )


# ── Tool: escalate_to_human ────────────────────────────────

def escalate_to_human(reason: str) -> str:
    """
    Flags conversation for human takeover.
    In production: send a Slack/email alert or create a support ticket.
    """
    logger.warning(f"ESCALATION REQUESTED: {reason}")
    # TODO: integrate with your support system (Slack, Zendesk, etc.)
    return (
        "I'm connecting you with a live support agent right now. "
        "Please hold for a moment — someone will be with you shortly."
    )


# ── Tool registry (used by agent.py) ──────────────────────

TOOLS = {
    "create_new_order":       create_new_order,
    "modify_existing_order":  modify_existing_order,
    "cancel_order":           cancel_order,
    "search_menu":            search_menu,
    "faq":                    faq,
    "get_order_history":      get_order_history,
    "issue_compensation":     issue_compensation,
    "escalate_to_human":      escalate_to_human,
}


def call_tool(name: str, args: dict) -> str:
    """Dispatch a tool call by name with given arguments."""
    fn = TOOLS.get(name)
    if fn is None:
        return f"Unknown tool: {name}"
    try:
        return fn(**args)
    except TypeError as e:
        logger.error(f"Tool {name} called with wrong args {args}: {e}")
        return f"Tool call failed: {e}"
