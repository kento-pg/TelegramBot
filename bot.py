import os
import asyncio
import logging
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
GROQ_API_KEY   = os.environ["GROQ_API_KEY"]
GROQ_URL       = "https://api.groq.com/openai/v1/chat/completions"
TG_API         = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

SYSTEM_PROMPT = """Kamu adalah asisten pribadi yang cerdas dan helpful.
Jawab dalam bahasa yang sama dengan pertanyaan pengguna (Indonesia atau Inggris).
Jawaban harus ringkas, jelas, dan langsung ke intinya."""

history: dict[int, list] = {}

def send_message(chat_id, text):
    requests.post(f"{TG_API}/sendMessage",
                  json={"chat_id": chat_id, "text": text}, timeout=10)

def send_typing(chat_id):
    requests.post(f"{TG_API}/sendChatAction",
                  json={"chat_id": chat_id, "action": "typing"}, timeout=5)

def ask_groq(chat_id, user_msg):
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

def get_updates(offset=None):
    params = {"timeout": 30}
    if offset:
        params["offset"] = offset
    resp = requests.get(f"{TG_API}/getUpdates", params=params, timeout=35)
    return resp.json().get("result", [])

def handle_update(update):
    msg     = update.get("message", {})
    chat_id = msg.get("chat", {}).get("id")
    text    = msg.get("text", "")
    if not chat_id or not text:
        return
    if text.startswith("/start"):
        send_message(chat_id, "Halo! Saya asisten AI Anda. Tanya apa saja!")
        return
    if text.startswith("/clear"):
        history.pop(chat_id, None)
        send_message(chat_id, "Riwayat percakapan dihapus.")
        return
    try:
        send_typing(chat_id)
        reply = ask_groq(chat_id, text)
        send_message(chat_id, reply)
    except Exception as e:
        logger.error(f"Error: {e}")
        send_message(chat_id, "Maaf, terjadi error. Coba lagi.")

def main():
    # Hapus webhook jika ada
    requests.post(f"{TG_API}/deleteWebhook", timeout=10)
    logger.info("Bot started (polling mode)")
    offset = None
    while True:
        try:
            updates = get_updates(offset)
            for update in updates:
                handle_update(update)
                offset = update["update_id"] + 1
        except Exception as e:
            logger.error(f"Polling error: {e}")

if __name__ == "__main__":
    main()
