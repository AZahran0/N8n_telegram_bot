"""
agent.py — Equivalent to the "AI Agent" node in n8n.

Receives the route + system prompt, runs the LLM with tool-use loop,
and returns the final response string.

Uses OpenRouter (Gemma primary, GLM fallback) with an agentic tool-call
loop: the model can call tools multiple times until it produces a final answer.
"""

import json
import logging
import httpx
from typing import Any

from config import OPENROUTER_API_KEY, PRIMARY_MODEL, FALLBACK_MODEL
from prompts import get_system_prompt
from tools import call_tool

logger = logging.getLogger(__name__)

# ── Tool schemas (what the LLM sees as available tools) ────

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "create_new_order",
            "description": "Places a brand new order into the database.",
            "parameters": {
                "type": "object",
                "properties": {
                    "items":  {"type": "array", "items": {"type": "string"}, "description": "List of item names"},
                    "name":   {"type": "string", "description": "Customer name"},
                    "phone":  {"type": "string", "description": "Customer phone number"},
                },
                "required": ["items", "name", "phone"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "modify_existing_order",
            "description": "Adds or removes items from an active order. Always verify order_id first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id":  {"type": "string"},
                    "action":    {"type": "string", "enum": ["add", "remove"]},
                    "item_name": {"type": "string"},
                },
                "required": ["order_id", "action", "item_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_order",
            "description": "Cancels an active order.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "reason":   {"type": "string"},
                },
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_menu",
            "description": "Queries the menu database for items, prices, descriptions, and allergen info.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "e.g. 'gluten free', 'pizza prices', 'vegan'"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "faq",
            "description": "Queries the FAQ with most frequently asked questions and answers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_order_history",
            "description": "Retrieves order details and status logs for a given order ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                },
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "issue_compensation",
            "description": "Applies a partial refund or issues a voucher. Max $15.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "type":     {"type": "string", "enum": ["refund", "voucher"]},
                    "amount":   {"type": "number", "description": "Dollar value, max 15"},
                },
                "required": ["order_id", "type", "amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_human",
            "description": "Transfers the conversation to a live support agent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string"},
                },
                "required": ["reason"],
            },
        },
    },
]


async def _call_openrouter(messages: list, model: str) -> dict:
    """Call OpenRouter and return the full response dict."""
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": messages,
                "tools": TOOL_SCHEMAS,
                "tool_choice": "auto",
                "max_tokens": 1000,
                "temperature": 0.7,
            }
        )
        response.raise_for_status()
        return response.json()


async def run_agent(
    route: str,
    user_message: str,
    chat_id: int,
    history: list[dict],
) -> str:
    """
    Main agent loop — equivalent to the AI Agent node in n8n.

    1. Builds messages with system prompt + history + new user message
    2. Calls the LLM
    3. If LLM calls a tool → execute it, append result, loop back
    4. If LLM returns text → return it as final response
    """
    system_prompt = get_system_prompt(route)

    # Build message list: system + history + current user message
    messages = [
        {"role": "system", "content": system_prompt},
        *history,
        {"role": "user", "content": user_message},
    ]

    MAX_TOOL_ITERATIONS = 5  # prevent infinite loops

    for model in [PRIMARY_MODEL, FALLBACK_MODEL]:
        try:
            for iteration in range(MAX_TOOL_ITERATIONS):
                logger.info(f"Agent iteration {iteration+1} with {model}")
                data = await _call_openrouter(messages, model)
                choice = data["choices"][0]
                message = choice["message"]
                finish_reason = choice.get("finish_reason", "")

                # ── Final text response ────────────────────
                if finish_reason == "stop" or (
                    not message.get("tool_calls") and message.get("content")
                ):
                    return message.get("content", "I'm not sure how to help with that.")

                # ── Tool calls requested ───────────────────
                tool_calls = message.get("tool_calls", [])
                if not tool_calls:
                    return message.get("content", "I'm not sure how to help with that.")

                # Append assistant message with tool calls to history
                messages.append(message)

                # Execute each tool call and append results
                for tc in tool_calls:
                    tool_name = tc["function"]["name"]
                    try:
                        tool_args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        tool_args = {}

                    logger.info(f"Tool call: {tool_name}({tool_args})")
                    result = call_tool(tool_name, tool_args)
                    logger.info(f"Tool result: {result[:100]}")

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result,
                    })

            # If we exhausted iterations without a final answer
            return "I'm having trouble processing your request. Please try again."

        except httpx.HTTPStatusError as e:
            logger.warning(f"HTTP error with {model}: {e.response.status_code}")
        except Exception as e:
            logger.warning(f"Agent error with {model}: {e}", exc_info=True)

    return "I'm experiencing technical difficulties. Please try again in a moment."
