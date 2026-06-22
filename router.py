"""
router.py — Equivalent to the "Basic LLM Chain" node in n8n.

Classifies user message into one of:
  general | order | questions | complaints

Uses Gemma via OpenRouter (with GLM as fallback).
"""

import json
import logging
import httpx
from config import OPENROUTER_API_KEY, PRIMARY_MODEL, FALLBACK_MODEL

logger = logging.getLogger(__name__)

ROUTER_SYSTEM_PROMPT = """You are an advanced intent-classification and routing assistant for a customer service system. Your sole task is to analyze the user's input and categorize it into exactly one of four routing destinations.

Analyze the user's message and output:
1. "route": The classified destination (must be exactly "general", "order", "questions", "complaints").

---

### Routing Categories

1. **general**
   - Criteria: Basic greetings, pleasantries, goodbyes, or polite chit-chat.
   - Examples: "Hello!", "Good morning", "Thanks for the help, bye", "How are you?"

2. **order**
   - Criteria: The user wants to execute a transactional action — placing, canceling, or modifying an order.
   - Examples: "I want to buy a burger", "Please cancel my order #1234", "Can I add fries?"

3. **questions**
   - Criteria: Seeking information about menu, prices, hours, or tracking a delivery.
   - Examples: "Do you have gluten-free options?", "How much is the pizza?", "What time do you close?"

4. **complaints**
   - Criteria: Expressing frustration or reporting an error (wrong items, cold food, late delivery).
   - Examples: "My burger is missing!", "This food is cold", "I've been waiting two hours!"

---

### Routing Priority (if multiple intents):
COMPLAINTS > ORDER > QUESTIONS > GENERAL

---

### Output Format
Return ONLY valid JSON. No markdown, no explanation, no extra characters.

Example:
{"route": "complaints"}"""


async def _call_openrouter(message: str, model: str) -> str:
    """Make a single call to OpenRouter and return raw text response."""
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
                    {"role": "user",   "content": message},
                ],
                "max_tokens": 50,
                "temperature": 0,  # deterministic for routing
            }
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()


async def classify_intent(user_message: str) -> str:
    """
    Classify user message into a route.
    Tries PRIMARY_MODEL first, falls back to FALLBACK_MODEL.
    Returns one of: 'general', 'order', 'questions', 'complaints'
    """
    valid_routes = {"general", "order", "questions", "complaints"}

    for model in [PRIMARY_MODEL, FALLBACK_MODEL]:
        try:
            raw = await _call_openrouter(user_message, model)
            data = json.loads(raw)
            route = data.get("route", "").lower().strip()

            if route in valid_routes:
                return route
            else:
                logger.warning(f"Invalid route '{route}' from {model}, trying fallback.")

        except json.JSONDecodeError:
            logger.warning(f"Non-JSON response from {model}: {raw!r}")
        except Exception as e:
            logger.warning(f"Router error with {model}: {e}")

    # Default to general if both models fail
    logger.error("Both models failed for routing. Defaulting to 'general'.")
    return "general"
