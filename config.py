"""
config.py — All credentials and settings
Replace placeholder values with your actual keys.
"""

import os

# ── Telegram ──────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")

# ── OpenRouter (Gemma + GLM models) ───────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "YOUR_OPENROUTER_API_KEY")
PRIMARY_MODEL   = "google/gemma-4-31b-it:free"
FALLBACK_MODEL  = "z-ai/glm-4.5-air:free"

# ── OpenAI (embeddings only) ───────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "YOUR_OPENAI_API_KEY")

# ── Supabase (vector store for menu + FAQ) ─────────────────
SUPABASE_URL     = os.getenv("SUPABASE_URL", "YOUR_SUPABASE_URL")
SUPABASE_API_KEY = os.getenv("SUPABASE_API_KEY", "YOUR_SUPABASE_API_KEY")

# ── Google Sheets (orders database) ───────────────────────
# Path to your downloaded service account JSON key file
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "google_credentials.json")
ORDERS_SHEET_ID         = os.getenv("ORDERS_SHEET_ID", "1sGkGORAjVu_wYB-AAOHubCZopwRtRMp3B0Ur7keQSb4")
ORDERS_SHEET_NAME       = os.getenv("ORDERS_SHEET_NAME", "الورقة1")

# ── Memory settings ────────────────────────────────────────
# How many past messages to keep in context window per user
MEMORY_WINDOW_SIZE = 10
