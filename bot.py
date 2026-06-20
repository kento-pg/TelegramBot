import os
import asyncio
import logging
import requests
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
GROQ_API_KEY   = os.environ["GROQ_API_KEY"]
GROQ_URL       = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM_PROMPT = """Kamu adalah asisten pribadi yang cerdas dan helpful.
Jawab dalam bahasa yang sama dengan pertanyaan pengguna (Indonesia atau Inggris).
Jawaban harus ringkas, jelas, dan langsung ke intinya."""

conversation_history: dict[int, list] = {}

def get_history(chat_id: int) -> list:
    if chat_id not in conversation_history:
        conversation_history[chat_id] = []
    return conversation_history[chat_id]

def trim_history(history: list, max_messages: int = 20):
    if len(history) > max_messages:
        conversation_history_trimmed = history[-max_messages:]
        history.clear()
        history.extend(conversation_history_trimmed)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Halo! Saya asisten AI Anda. Tanya apa saja, saya siap membantu!"
    )

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    conversation_history[chat_id] = []
    await update.message.reply_text("Riwayat percakapan dihapus.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id  = update.effective_chat.id
    user_msg = update.message.text

    history = get_history(chat_id)
    history.append({"role": "user", "content": user_msg})
    trim_history(history)

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    try:
        resp = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.1-8b-instant",
                "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + history,
                "max_tokens": 1024,
                "temperature": 0.7,
            },
            timeout=30,
        )
        resp.raise_for_status()
        reply = resp.json()["choices"][0]["message"]["content"]
        history.append({"role": "assistant", "content": reply})
        await update.message.reply_text(reply)

    except Exception as e:
        logger.error(f"Groq error: {e}")
        await update.message.reply_text("Maaf, terjadi error. Coba lagi.")

def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()
