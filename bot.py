import os
import re
import json
import threading
import logging
import requests
import xml.etree.ElementTree as ET
from http.server import HTTPServer, BaseHTTPRequestHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
GROQ_API_KEY   = os.environ["GROQ_API_KEY"]
GROQ_URL       = "https://api.groq.com/openai/v1/chat/completions"
TG_API         = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

SYSTEM_PROMPT = """Kamu adalah asisten pribadi yang cerdas dan helpful.
Jawab dalam bahasa yang sama dengan pertanyaan pengguna (Indonesia atau Inggris).
Jawaban harus ringkas, jelas, dan langsung ke intinya."""

SEARCH_KEYWORDS = [
    "hari ini", "sekarang", "skrg", "terbaru", "kemarin", "harga", "berapa",
    "naik", "turun", "berita", "kondisi", "update", "today", "latest",
    "current", "now", "recent", "news", "price", "market",
]

BINANCE_SYMBOLS = {
    "btc": "BTCUSDT", "bitcoin": "BTCUSDT",
    "eth": "ETHUSDT", "ethereum": "ETHUSDT",
    "sol": "SOLUSDT", "solana": "SOLUSDT",
    "bnb": "BNBUSDT", "xrp": "XRPUSDT",
    "doge": "DOGEUSDT", "ada": "ADAUSDT",
    "avax": "AVAXUSDT", "dot": "DOTUSDT",
}

history: dict[int, list] = {}

# Diagnostic state — readable via health endpoint
diag: dict = {
    "polling_started": False,
    "updates_received": 0,
    "updates_processed": 0,
    "last_update_id": None,
    "last_error": None,
    "send_ok": 0,
    "send_fail": 0,
    "getme": None,
}


def send_message(chat_id, text):
    try:
        r = requests.post(f"{TG_API}/sendMessage",
                          json={"chat_id": chat_id, "text": text}, timeout=10)
        if r.status_code == 200:
            diag["send_ok"] += 1
        else:
            diag["send_fail"] += 1
            diag["last_error"] = f"sendMessage {r.status_code}: {r.text[:100]}"
            logger.error(diag["last_error"])
    except Exception as e:
        diag["send_fail"] += 1
        diag["last_error"] = f"sendMessage exc: {e}"
        logger.error(diag["last_error"])


def send_typing(chat_id):
    try:
        requests.post(f"{TG_API}/sendChatAction",
                      json={"chat_id": chat_id, "action": "typing"}, timeout=5)
    except Exception:
        pass


def get_crypto_price(text: str) -> str:
    t = text.lower()
    symbol = next((BINANCE_SYMBOLS[k] for k in BINANCE_SYMBOLS if k in t), None)
    if not symbol:
        return ""
    try:
        resp = requests.get("https://api.binance.com/api/v3/ticker/price",
                            params={"symbol": symbol}, timeout=8)
        price = float(resp.json()["price"])
        return f"{symbol.replace('USDT','')}: ${price:,.2f} USDT (Binance realtime)"
    except Exception as e:
        logger.warning(f"Binance failed: {e}")
        return ""


def web_search(query: str) -> str:
    try:
        resp = requests.get(
            "https://news.google.com/rss/search",
            params={"q": query, "hl": "id", "gl": "ID", "ceid": "ID:id"},
            timeout=8, headers={"User-Agent": "Mozilla/5.0"},
        )
        root = ET.fromstring(resp.content)
        headlines = []
        for item in root.findall(".//item")[:5]:
            title = item.findtext("title", "").split(" - ")[0].strip()
            if title:
                headlines.append(f"- {title}")
        return "Berita terkini:\n" + "\n".join(headlines) if headlines else ""
    except Exception as e:
        logger.warning(f"News search failed: {e}")
        return ""


def extract_url(text: str) -> str:
    m = re.search(r'https?://\S+', text)
    return m.group(0) if m else ""


def fetch_url_text(url: str) -> str:
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        text = re.sub(r'<[^>]+>', ' ', resp.text)
        return re.sub(r'\s+', ' ', text).strip()[:3000]
    except Exception as e:
        logger.warning(f"URL fetch failed: {e}")
        return ""


def ask_groq(messages: list, system: str = SYSTEM_PROMPT) -> str:
    for attempt in range(3):
        try:
            resp = requests.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {GROQ_API_KEY}",
                         "Content-Type": "application/json"},
                json={"model": "llama-3.1-8b-instant",
                      "messages": [{"role": "system", "content": system}] + messages,
                      "max_tokens": 1024, "temperature": 0.7},
                timeout=45,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning(f"Groq attempt {attempt+1} failed: {e}")
            if attempt == 2:
                return f"Error Groq: {str(e)[:100]}"
    return "Maaf, terjadi error."


def analyze_photo_url(file_id: str, caption: str) -> str:
    try:
        r = requests.get(f"{TG_API}/getFile", params={"file_id": file_id}, timeout=10)
        r.raise_for_status()
        file_path = r.json()["result"]["file_path"]
        img_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
        prompt = caption if caption else "Jelaskan isi gambar ini secara detail."
        resp = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}",
                     "Content-Type": "application/json"},
            json={
                "model": "llama-3.2-11b-vision-preview",
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": img_url}},
                ]}],
                "max_tokens": 1024,
            },
            timeout=45,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"Photo analysis failed: {e}")
        return f"Gagal analisa foto: {str(e)[:150]}"


def handle_update(update):
    msg = update.get("message") or update.get("edited_message") or {}
    if not msg:
        return
    chat_id = msg.get("chat", {}).get("id")
    if not chat_id:
        return

    diag["updates_processed"] += 1

    # ── Photo ──────────────────────────────────────────────────────────────────
    photos = msg.get("photo")
    if photos:
        send_message(chat_id, "Foto diterima, sedang dianalisa...")
        file_id = photos[-1]["file_id"]
        caption = msg.get("caption", "")
        reply = analyze_photo_url(file_id, caption)
        send_message(chat_id, reply)
        return

    # ── Text ───────────────────────────────────────────────────────────────────
    text = msg.get("text", "")
    if not text:
        return

    if text.startswith("/start"):
        send_message(chat_id,
            "Halo! Saya Kina, asisten AI Anda.\n"
            "- Tanya apa saja\n"
            "- Kirim foto untuk dianalisa\n"
            "- Kirim link untuk dirangkum\n"
            "- /clear hapus riwayat")
        return
    if text.startswith("/clear"):
        history.pop(chat_id, None)
        send_message(chat_id, "Riwayat percakapan dihapus.")
        return
    if text.startswith("/debug"):
        binance = get_crypto_price("btc") or "GAGAL"
        info = (
            f"SHA: 631d40a\n"
            f"updates_received: {diag['updates_received']}\n"
            f"updates_processed: {diag['updates_processed']}\n"
            f"send_ok: {diag['send_ok']}\n"
            f"send_fail: {diag['send_fail']}\n"
            f"last_error: {diag['last_error']}\n"
            f"Binance: {binance}"
        )
        send_message(chat_id, info)
        return

    send_typing(chat_id)

    crypto = get_crypto_price(text)
    if crypto:
        send_message(chat_id, crypto)
        return

    url = extract_url(text)
    if url:
        send_message(chat_id, f"Membaca {url}...")
        page = fetch_url_text(url)
        msgs = [{"role": "user", "content": f"Isi halaman: {page}\n\nPertanyaan: {text}"}] if page else [{"role": "user", "content": text}]
        send_message(chat_id, ask_groq(msgs))
        return

    if any(kw in text.lower() for kw in SEARCH_KEYWORDS):
        news = web_search(text)
        if news:
            send_message(chat_id, news)
            return

    msgs = history.setdefault(chat_id, [])
    msgs.append({"role": "user", "content": text})
    if len(msgs) > 10:
        msgs[:] = msgs[-10:]
    reply = ask_groq(msgs)
    msgs.append({"role": "assistant", "content": reply})
    send_message(chat_id, reply)


def polling_loop():
    # Verify token works
    try:
        r = requests.get(f"{TG_API}/getMe", timeout=10)
        diag["getme"] = r.json()
    except Exception as e:
        diag["getme"] = f"ERROR: {e}"
        diag["last_error"] = str(e)

    requests.post(f"{TG_API}/deleteWebhook", timeout=15)
    diag["polling_started"] = True
    logger.info("Bot polling started")
    offset = None
    while True:
        try:
            params = {"timeout": 30, "offset": offset} if offset else {"timeout": 30}
            resp = requests.get(f"{TG_API}/getUpdates", params=params, timeout=40)
            updates = resp.json().get("result", [])
            diag["updates_received"] += len(updates)
            for update in updates:
                try:
                    handle_update(update)
                except Exception as e:
                    diag["last_error"] = f"handle_update: {e}"
                    logger.error(diag["last_error"])
                offset = update["update_id"] + 1
                diag["last_update_id"] = offset - 1
        except Exception as e:
            diag["last_error"] = f"polling: {e}"
            logger.error(diag["last_error"])


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps(diag, default=str, indent=2).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    threading.Thread(target=polling_loop, daemon=True).start()
    logger.info("Health server on port 7860")
    HTTPServer(("0.0.0.0", 7860), HealthHandler).serve_forever()
