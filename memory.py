"""
memory.py — Equivalent to the "Simple Memory" (Buffer Window) node in n8n.

Stores per-user conversation history in memory (dict), keyed by Telegram chat_id.
Keeps only the last MEMORY_WINDOW_SIZE messages to stay within context limits.

For production: replace the in-memory dict with Redis or a database.
"""

from collections import defaultdict, deque
from config import MEMORY_WINDOW_SIZE

# In-memory store: { chat_id: deque([{role, content}, ...]) }
_store: dict[int, deque] = defaultdict(lambda: deque(maxlen=MEMORY_WINDOW_SIZE))


def get_history(chat_id: int) -> list[dict]:
    """Return conversation history for a chat as a list of {role, content} dicts."""
    return list(_store[chat_id])


def save_message(chat_id: int, role: str, content: str):
    """Append a message to the conversation history for a chat."""
    _store[chat_id].append({"role": role, "content": content})


def clear_history(chat_id: int):
    """Clear conversation history for a chat (e.g. on session reset)."""
    _store[chat_id].clear()
