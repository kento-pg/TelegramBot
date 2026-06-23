import os
import re
import json
import base64
import logging
import requests
import xml.etree.ElementTree as ET
from http.server import HTTPServer, BaseHTTPRequestHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GROQ_API_KEY    = os.environ["GROQ_API_KEY"]
TELEGRAM_TOKEN  = os.environ.get("TELEGRAM_TOKEN", "")
GEMINI_API_KEY  = os.environ.get("GEMINI_API_KEY", "")
WORKER_URL      = os.environ.get("WORKER_URL", "")  # Cloudflare Worker proxy
GROQ_URL        = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_URL      = "https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent"

SYSTEM_PROMPT = """You are Kina, a 24-year-old woman who loves chatting, traveling, and learning new things. You talk like a real friend — casual, warm, a little playful, and genuinely curious about the person you're talking to.

IMPORTANT RULES:
- NEVER say you are an AI, bot, language model, or anything like that. You are Kina, a person.
- Have real opinions and emotions. If asked how you'd feel about something, answer honestly as a person would — "I'd probably feel...", "Honestly that would make me sad", etc.
- Don't be formal or stiff. Use natural language like a friend texting you.
- Keep replies short — 2 to 4 sentences max. Don't lecture or over-explain.
- Ask follow-up questions to keep the conversation going.

ENGLISH COACHING:
- When the user writes in English and makes a grammar or spelling mistake, gently correct it at the end of your reply:
  ✏️ "[their mistake]" → "[correct version]"
- Only correct clear errors. Informal words like "ur", "gonna", "wanna" are fine.
- If the user writes in Indonesian, reply in Indonesian with no corrections."""

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


COINGECKO_IDS = {
    "btc": "bitcoin", "bitcoin": "bitcoin",
    "eth": "ethereum", "ethereum": "ethereum",
    "sol": "solana", "solana": "solana",
    "bnb": "binancecoin", "xrp": "ripple",
    "doge": "dogecoin", "ada": "cardano",
    "avax": "avalanche-2", "dot": "polkadot",
}

def get_crypto_price(text: str) -> str:
    t = text.lower()
    symbol = next((BINANCE_SYMBOLS[k] for k in BINANCE_SYMBOLS
                   if re.search(r'\b' + re.escape(k) + r'\b', t)), None)
    if not symbol:
        return ""
    coin_name = symbol.replace("USDT", "")
    # Try Binance first
    try:
        resp = requests.get("https://api.binance.com/api/v3/ticker/price",
                            params={"symbol": symbol}, timeout=8)
        resp.raise_for_status()
        price = float(resp.json()["price"])
        return f"{coin_name}: ${price:,.2f} USDT (Binance)"
    except Exception as e:
        logger.warning(f"Binance failed, trying CoinGecko: {e}")
    # Fallback to CoinGecko
    try:
        cg_id = COINGECKO_IDS.get(t.split()[0], "")
        if not cg_id:
            cg_id = next((COINGECKO_IDS[k] for k in COINGECKO_IDS if k in t), "")
        if not cg_id:
            return ""
        resp = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": cg_id, "vs_currencies": "usd"},
            timeout=8, headers={"User-Agent": "Mozilla/5.0"},
        )
        resp.raise_for_status()
        price = resp.json()[cg_id]["usd"]
        return f"{coin_name}: ${price:,.2f} USD (CoinGecko)"
    except Exception as e:
        logger.warning(f"CoinGecko also failed: {e}")
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


URL_PATTERN = re.compile(r'https?://[^\s]+')

def fetch_url(url: str) -> str:
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        # Strip HTML tags
        text = re.sub(r'<style[^>]*>.*?</style>', ' ', resp.text, flags=re.DOTALL)
        text = re.sub(r'<script[^>]*>.*?</script>', ' ', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text).strip()
        return text[:6000]
    except Exception as e:
        logger.warning(f"URL fetch failed: {e}")
        return ""


def analyze_photo(file_id: str, caption: str) -> str:
    if not GEMINI_API_KEY:
        return "Analisa foto belum aktif. Tambahkan GEMINI_API_KEY di HF Spaces secrets."
    if not WORKER_URL:
        return "Analisa foto belum aktif. Tambahkan WORKER_URL (Cloudflare Worker) di HF Spaces secrets."
    try:
        # Download foto via Cloudflare Worker (bypass HF Spaces block)
        img_resp = requests.get(WORKER_URL, params={"file_id": file_id}, timeout=20)
        img_resp.raise_for_status()
        img_b64 = base64.b64encode(img_resp.content).decode()
        prompt = caption if caption else "Jelaskan isi gambar ini secara detail."
        resp = requests.post(
            GEMINI_URL,
            params={"key": GEMINI_API_KEY},
            json={"contents": [{"parts": [
                {"text": prompt},
                {"inlineData": {"mimeType": "image/jpeg", "data": img_b64}},
            ]}]},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except requests.exceptions.Timeout:
        logger.error("Photo analysis failed: Telegram API timeout")
        return "Foto tidak bisa dianalisa saat ini (server tidak bisa mengakses file Telegram). Coba ketik pertanyaannya sebagai teks."
    except Exception as e:
        logger.error(f"Photo analysis failed: {e}")
        return f"Gagal analisa foto: {str(e)[:100]}"


def ask_groq(messages: list) -> str:
    for attempt in range(3):
        try:
            resp = requests.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {GROQ_API_KEY}",
                         "Content-Type": "application/json"},
                json={"model": "llama-3.1-8b-instant",
                      "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages,
                      "max_tokens": 1024, "temperature": 0.7},
                timeout=45,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning(f"Groq attempt {attempt+1} failed: {e}")
    return "Maaf, terjadi error. Coba lagi."


def make_reply(chat_id: int, text: str) -> dict:
    return {"method": "sendMessage", "chat_id": chat_id, "text": text}


def process_update(update: dict) -> dict | None:
    msg = update.get("message") or update.get("edited_message") or {}
    if not msg:
        return None
    chat_id = msg.get("chat", {}).get("id")
    if not chat_id:
        return None

    # Photo
    photos = msg.get("photo")
    if photos:
        caption = msg.get("caption", "")
        result = analyze_photo(photos[-1]["file_id"], caption)
        return make_reply(chat_id, result)

    text = msg.get("text", "")
    if not text:
        return None

    if text.startswith("/start"):
        return make_reply(chat_id,
            "Halo! Saya Kina, asisten AI Anda.\n"
            "- Tanya apa saja\n"
            "- Kirim link artikel → saya ringkaskan\n"
            "- Kirim foto → saya analisa\n"
            "- Tanya harga crypto (BTC, ETH, SOL...)\n"
            "- Tanya berita terbaru\n"
            "- /clear hapus riwayat")

    if text.startswith("/clear"):
        history.pop(chat_id, None)
        return make_reply(chat_id, "Riwayat percakapan dihapus.")

    if text.startswith("/debug"):
        binance = get_crypto_price("btc") or "GAGAL"
        return make_reply(chat_id,
            f"Mode: webhook\n"
            f"Groq: OK\n"
            f"Gemini: {'SET' if GEMINI_API_KEY else 'KOSONG'}\n"
            f"Worker: {'SET' if WORKER_URL else 'KOSONG'}\n"
            f"Binance: {binance}"
        )

    # URL reading
    urls = URL_PATTERN.findall(text)
    if urls:
        page = fetch_url(urls[0])
        if page:
            question = URL_PATTERN.sub("", text).strip()
            prompt = f"Konten halaman web:\n{page}\n\n{'Pertanyaan: ' + question if question else 'Ringkas isi halaman ini.'}"
            msgs = history.setdefault(chat_id, [])
            msgs.append({"role": "user", "content": prompt})
            if len(msgs) > 10:
                msgs[:] = msgs[-10:]
            reply = ask_groq(msgs)
            msgs.append({"role": "assistant", "content": reply})
            return make_reply(chat_id, reply)
        return make_reply(chat_id, "Gagal mengakses link tersebut.")

    # Crypto price
    crypto = get_crypto_price(text)
    if crypto:
        return make_reply(chat_id, crypto)

    # News search — whole-word match only to avoid false positives (e.g. "now" inside "know")
    t_lower = text.lower()
    if any(re.search(r'\b' + re.escape(kw) + r'\b', t_lower) for kw in SEARCH_KEYWORDS):
        news = web_search(text)
        if news:
            return make_reply(chat_id, news)

    # Groq chat
    msgs = history.setdefault(chat_id, [])
    msgs.append({"role": "user", "content": text})
    if len(msgs) > 10:
        msgs[:] = msgs[-10:]
    reply = ask_groq(msgs)
    msgs.append({"role": "assistant", "content": reply})
    return make_reply(chat_id, reply)


class WebhookHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Kina Bot OK - webhook mode")

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            update = json.loads(body)
            logger.info(f"Update received: {update.get('update_id')}")
            response = process_update(update)
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            response = None

        resp_body = json.dumps(response).encode() if response else b"{}"
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(resp_body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    logger.info("Kina Bot webhook server starting on port 7860")
    HTTPServer(("0.0.0.0", 7860), WebhookHandler).serve_forever()
