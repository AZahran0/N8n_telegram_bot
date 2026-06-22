"""
Telegram RAG Bot - Python equivalent of the n8n workflow
Entry point: starts the Telegram bot and handles incoming messages
"""

import asyncio
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

from config import TELEGRAM_BOT_TOKEN
from router import classify_intent
from agent import run_agent
from memory import get_history, save_message

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Main handler — equivalent to the full n8n workflow chain:
    Telegram Trigger → Router → Switch → AI Agent → Send Message
    """
    chat_id = update.message.chat.id
    user_message = update.message.text

    if not user_message:
        return

    logger.info(f"[{chat_id}] User: {user_message}")

    # Show typing indicator while processing
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    try:
        # Step 1: Classify intent (Basic LLM Chain node)
        route = await classify_intent(user_message)
        logger.info(f"[{chat_id}] Route: {route}")

        # Step 2: Get conversation memory (Simple Memory node)
        history = get_history(chat_id)

        # Step 3: Run AI agent with correct system prompt + tools (AI Agent node)
        response = await run_agent(
            route=route,
            user_message=user_message,
            chat_id=chat_id,
            history=history
        )

        # Step 4: Save messages to memory
        save_message(chat_id, "user", user_message)
        save_message(chat_id, "assistant", response)

        # Step 5: Send reply (Send a text message node)
        await update.message.reply_text(response)
        logger.info(f"[{chat_id}] Bot: {response[:80]}...")

    except Exception as e:
        logger.error(f"[{chat_id}] Error: {e}", exc_info=True)
        await update.message.reply_text(
            "Sorry, I encountered an issue. Please try again in a moment."
        )


def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot started. Listening for messages...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
