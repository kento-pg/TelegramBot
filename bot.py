import os
import threading
import logging
import requests
import xml.etree.ElementTree as ET
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

BINANCE_SYMBOLS = {
    "btc": "BTCUSDT", "bitcoin": "BTCUSDT",
    "eth": "ETHUSDT", "ethereum": "ETHUSDT",
    "sol": "SOLUSDT", "solana": "SOLUSDT",
    "bnb": "BNBUSDT",
    "xrp": "XRPUSDT",
    "doge": "DOGEUSDT",
    "ada": "ADAUSDT",
    "avax": "AVAXUSDT",
    "dot": "DOTUSDT",
    "matic": "MATICUSDT",
    "link": "LINKUSDT",
    "uni": "UNIUSDT",
}

logger.info(f"TAVILY_API_KEY loaded: {'YES' if TAVILY_API_KEY else 'NO'}")

history: dict[int, list] = {}


def needs_search(text: str) -> bool:
    t = text.lower()
    return any(kw in t for kw in SEARCH_KEYWORDS)


def get_crypto_price(text: str) -> str:
    """Fetch live crypto price from Binance (no API key, no rate limit)."""
    t = text.lower()
    symbol = next((BINANCE_SYMBOLS[k] for k in BINANCE_SYMBOLS if k in t), None)
    if not symbol:
        return ""
    try:
        resp = requests.get(
            "https://api.binance.com/api/v3/ticker/price",
            params={"symbol": symbol},
            timeout=8,
        )
        data = resp.json()
        price = float(data["price"])
        coin = symbol.replace("USDT", "")
        return f"💰 {coin}: ${price:,.2f} USDT (Binance, realtime)"
    except Exception as e:
        logger.warning(f"Binance failed: {e}")
        return ""


def web_search(query: str) -> tuple[str, str]:
    """Fetch latest news from Google News RSS (no API key needed)."""
    try:
        url = "https://news.google.com/rss/search"
        resp = requests.get(url, params={"q": query, "hl": "id", "gl": "ID", "ceid": "ID:id"},
                            timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        root = ET.fromstring(resp.content)
        items = root.findall(".//item")[:5]
        headlines = []
        for item in items:
            title = item.findtext("title", "").split(" - ")[0].strip()
            desc = item.findtext("description", "")[:150].strip()
            if title:
                headlines.append(f"• {title}: {desc}" if desc else f"• {title}")
        if not headlines:
            return "", ""
        return f"Berita terbaru tentang '{query}':", "\n".join(headlines)
    except Exception as e:
        logger.warning(f"News search failed: {e}")
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
        # Test 1: Binance crypto price
        binance_test = get_crypto_price("btc") or "GAGAL ✗"
        # Test 2: Google News RSS
        news_test = "GAGAL ✗"
        try:
            answer, details = web_search("bitcoin")
            news_test = f"OK ✓ — {details[:80]}" if (answer or details) else "KOSONG"
        except Exception as e:
            news_test = f"ERROR: {str(e)[:60]}"
        send_message(chat_id,
            f"GROQ: {'SET ✓' if GROQ_API_KEY else 'KOSONG ✗'}\n"
            f"Binance price: {binance_test}\n"
            f"Google News: {news_test}"
        )
        return
    try:
        send_typing(chat_id)
        # Crypto price: use CoinGecko directly (always works)
        crypto_reply = get_crypto_price(text)
        if crypto_reply:
            send_message(chat_id, crypto_reply)
            return
        # General current-info: try Tavily
        if needs_search(text):
            answer, details = web_search(text)
            if answer or details:
                reply = f"🔍 {answer}" if answer else ""
                if details:
                    reply += ("\n\n" if reply else "") + details
                send_message(chat_id, reply.strip())
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
