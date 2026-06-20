import os
import logging
import requests
from flask import Flask, request, Response
from telegram import Update, Bot
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
GROQ_API_KEY   = os.environ["GROQ_API_KEY"]
SPACE_URL       = os.environ.get("SPACE_URL", "")
GROQ_URL        = "https://api.groq.com/openai/v1/chat/completions"
PORT            = int(os.environ.get("PORT", 7860))

SYSTEM_PROMPT = """Kamu adalah asisten pribadi yang cerdas dan helpful.
Jawab dalam bahasa yang sama dengan pertanyaan pengguna (Indonesia atau Inggris).
Jawaban harus ringkas, jelas, dan langsung ke intinya."""

conversation_history: dict[int, list] = {}
app_flask = Flask(__name__)

def get_history(chat_id: int) -> list:
    if chat_id not in conversation_history:
        conversation_history[chat_id] = []
    return conversation_history[chat_id]

def trim_history(history: list, max_messages: int = 20):
    if len(history) > max_messages:
        trimmed = history[-max_messages:]
        history.clear()
        history.extend(trimmed)

def ask_groq(history: list) -> str:
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
    return resp.json()["choices"][0]["message"]["content"]

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
        reply = ask_groq(history)
        history.append({"role": "assistant", "content": reply})
        await update.message.reply_text(reply)
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("Maaf, terjadi error. Coba lagi.")

ptb_app = Application.builder().token(TELEGRAM_TOKEN).updater(None).build()
ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(CommandHandler("clear", clear))
ptb_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

@app_flask.route("/", methods=["GET"])
def health():
    return Response("OK", status=200)

@app_flask.route(f"/webhook/{TELEGRAM_TOKEN}", methods=["POST"])
def webhook():
    import asyncio
    data = request.get_json(force=True)
    update = Update.de_json(data, ptb_app.bot)
    asyncio.run(ptb_app.process_update(update))
    return Response("OK", status=200)

def set_webhook():
    if not SPACE_URL:
        logger.warning("SPACE_URL not set, skipping webhook registration")
        return
    url = f"{SPACE_URL}/webhook/{TELEGRAM_TOKEN}"
    r = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook",
        json={"url": url},
        timeout=10,
    )
    logger.info(f"Webhook set: {r.json()}")

if __name__ == "__main__":
    logger.info(f"Starting webhook server on port {PORT}")
    app_flask.run(host="0.0.0.0", port=PORT)
