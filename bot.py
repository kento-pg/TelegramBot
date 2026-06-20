import os
import logging
import requests
from flask import Flask, request, jsonify

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
GROQ_API_KEY   = os.environ["GROQ_API_KEY"]
GROQ_URL       = "https://api.groq.com/openai/v1/chat/completions"
TG_API        = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
PORT           = int(os.environ.get("PORT", 7860))

SYSTEM_PROMPT = """Kamu adalah asisten pribadi yang cerdas dan helpful.
Jawab dalam bahasa yang sama dengan pertanyaan pengguna (Indonesia atau Inggris).
Jawaban harus ringkas, jelas, dan langsung ke intinya."""

history: dict[int, list] = {}
app = Flask(__name__)

def send_message(chat_id: int, text: str):
    requests.post(f"{TG_API}/sendMessage",
                  json={"chat_id": chat_id, "text": text}, timeout=10)

def send_typing(chat_id: int):
    requests.post(f"{TG_API}/sendChatAction",
                  json={"chat_id": chat_id, "action": "typing"}, timeout=5)

def ask_groq(chat_id: int, user_msg: str) -> str:
    msgs = history.setdefault(chat_id, [])
    msgs.append({"role": "user", "content": user_msg})
    if len(msgs) > 20:
        msgs[:] = msgs[-20:]

    resp = requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {GROQ_API_KEY}",
                 "Content-Type": "application/json"},
        json={"model": "llama-3.1-8b-instant",
              "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + msgs,
              "max_tokens": 1024, "temperature": 0.7},
        timeout=30,
    )
    resp.raise_for_status()
    reply = resp.json()["choices"][0]["message"]["content"]
    msgs.append({"role": "assistant", "content": reply})
    return reply

@app.get("/")
def health():
    return "OK", 200

@app.post("/webhook")
def webhook():
    try:
        data    = request.get_json(silent=True) or {}
        msg     = data.get("message", {})
        chat_id = msg.get("chat", {}).get("id")
        text    = msg.get("text", "")

        if not chat_id or not text:
            return "OK", 200

        if text.startswith("/start"):
            send_message(chat_id, "Halo! Saya asisten AI Anda. Tanya apa saja!")
            return "OK", 200

        if text.startswith("/clear"):
            history.pop(chat_id, None)
            send_message(chat_id, "Riwayat percakapan dihapus.")
            return "OK", 200

        send_typing(chat_id)
        reply = ask_groq(chat_id, text)
        send_message(chat_id, reply)

    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)

    return "OK", 200

if __name__ == "__main__":
    logger.info(f"Bot starting on port {PORT}")
    app.run(host="0.0.0.0", port=PORT)
