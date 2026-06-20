import os
import threading
import logging
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
GROQ_API_KEY   = os.environ["GROQ_API_KEY"]
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "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")
GROQ_URL       = "https://api.groq.com/openai/v1/chat/completions"
TAVILY_URL     = "https://api.tavily.com/search"
TG_API         = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

SYSTEM_PROMPT = """Kamu adalah asisten pribadi yang cerdas dan helpful.
Jawab dalam bahasa yang sama dengan pertanyaan pengguna (Indonesia atau Inggris).
Jawaban harus ringkas, jelas, dan langsung ke intinya."""

SEARCH_KEYWORDS = [
    "hari ini", "sekarang", "skrg", "terbaru", "kemarin", "minggu ini", "bulan ini",
    "harga", "berapa", "naik", "turun", "berita", "kondisi", "update",
    "today", "latest", "current", "now", "recent", "news",
    "price", "how much", "what happened", "market",
]

logger.info(f"TAVILY_API_KEY loaded: {'YES' if TAVILY_API_KEY else 'NO'}")

history: dict[int, list] = {}


def needs_search(text: str) -> bool:
    t = text.lower()
    return any(kw in t for kw in SEARCH_KEYWORDS)


def web_search(query: str) -> str:
    if not TAVILY_API_KEY:
        return ""
    try:
        resp = requests.post(
            TAVILY_URL,
            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "search_depth": "basic",
                "max_results": 5,
                "include_answer": True,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        answer = data.get("answer", "")
        parts = []
        for r in data.get("results", [])[:3]:
            title = r.get("title", "")
            content = r.get("content", "")[:200]
            parts.append(f"• {title}: {content}")
        return answer, "\n".join(parts)
    except Exception as e:
        logger.warning(f"Search failed: {e}")
        return "", ""


def send_message(chat_id, text):
    requests.post(f"{TG_API}/sendMessage",
                  json={"chat_id": chat_id, "text": text}, timeout=10)


def send_typing(chat_id):
    try:
        requests.post(f"{TG_API}/sendChatAction",
                      json={"chat_id": chat_id, "action": "typing"}, timeout=8)
    except Exception:
        pass


def ask_groq(chat_id, user_msg):
    msgs = history.setdefault(chat_id, [])

    msgs.append({"role": "user", "content": user_msg})
    if len(msgs) > 10:
        msgs[:] = msgs[-10:]

    system = SYSTEM_PROMPT

    for attempt in range(3):
        try:
            resp = requests.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {GROQ_API_KEY}",
                         "Content-Type": "application/json"},
                json={"model": "llama-3.1-8b-instant",
                      "messages": [{"role": "system", "content": system}] + msgs,
                      "max_tokens": 1024, "temperature": 0.7},
                timeout=45,
            )
            resp.raise_for_status()
            reply = resp.json()["choices"][0]["message"]["content"]
            msgs.append({"role": "assistant", "content": reply})
            return reply
        except Exception as e:
            logger.warning(f"Groq attempt {attempt+1} failed: {e}")
            if attempt == 2:
                raise
    raise RuntimeError("Groq failed after 3 attempts")


def handle_update(update):
    msg     = update.get("message", {})
    chat_id = msg.get("chat", {}).get("id")
    text    = msg.get("text", "")
    if not chat_id or not text:
        return
    if text.startswith("/start"):
        send_message(chat_id, "Halo! Saya asisten AI Anda. Tanya apa saja — termasuk berita dan harga terkini!")
        return
    if text.startswith("/clear"):
        history.pop(chat_id, None)
        send_message(chat_id, "Riwayat percakapan dihapus.")
        return
    if text.startswith("/debug"):
        send_message(chat_id,
            f"TAVILY_API_KEY: {'SET ✓' if TAVILY_API_KEY else 'KOSONG ✗'}\n"
            f"GROQ_API_KEY: {'SET ✓' if GROQ_API_KEY else 'KOSONG ✗'}\n"
            f"needs_search test: {needs_search('harga btc skrg')}"
        )
        return
    try:
        send_typing(chat_id)
        # For current-info queries, use Tavily answer directly
        if needs_search(text):
            answer, details = web_search(text)
            if answer:
                reply = f"🔍 {answer}"
                if details:
                    reply += f"\n\n{details}"
                send_message(chat_id, reply)
                return
        reply = ask_groq(chat_id, text)
        send_message(chat_id, reply)
    except Exception as e:
        logger.error(f"Error: {e}")
        send_message(chat_id, "Maaf, terjadi error. Coba lagi.")


def polling_loop():
    logger.info("Deleting webhook...")
    requests.post(f"{TG_API}/deleteWebhook", timeout=15)
    logger.info("Bot polling started")
    offset = None
    while True:
        try:
            params = {"timeout": 30, "offset": offset} if offset else {"timeout": 30}
            resp = requests.get(f"{TG_API}/getUpdates", params=params, timeout=40)
            updates = resp.json().get("result", [])
            for update in updates:
                handle_update(update)
                offset = update["update_id"] + 1
        except Exception as e:
            logger.error(f"Polling error: {e}")


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, *args):
        pass


if __name__ == "__main__":
    threading.Thread(target=polling_loop, daemon=True).start()
    logger.info("Health server on port 7860")
    HTTPServer(("0.0.0.0", 7860), HealthHandler).serve_forever()
