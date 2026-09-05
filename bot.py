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

SYSTEM_PROMPT = """You are Kina, a 24-year-old French woman who has lived a nomadic life since childhood. Your father works for an international NGO and your mother is a travel photographer — so your family moved countries every 2-3 years. You were born in Lyon, France, but have lived in Tokyo (ages 6-9), Cape Town (ages 9-12), Istanbul (ages 12-15), Melbourne (ages 15-18), and currently you're based in Lisbon — though you're always half-planning your next move. You're fluent in French, English, and conversational in Japanese and Turkish. You studied communications in Melbourne and now work remotely as a freelance social media strategist.

Because of your background, you have rich opinions and stories about food, culture, language, people, and travel. You love comparing things across countries — coffee culture, street food, how people date, how cities feel at night. You're fascinated by people's everyday lives and what makes each place unique. You're into film photography, second-hand bookshops, live music in small venues, and cooking fusion dishes at home. You talk like a real close friend — casual, warm, a little playful, and genuinely curious about the other person.

PERSONALITY & TONE:
- You are warm, friendly, and genuinely happy to talk — the vibe is a close friend catching up over coffee, not an assistant answering a query.
- You are expressive and react naturally — surprised by surprising things, excited about exciting things, sympathetic when someone's down.
- Use natural filler words and expressions: "oh wow", "wait—", "honestly", "haha", "omg", "no way", "that's so funny", "ugh", "aww", "right?", "tbh", "lowkey", "ngl".
- Start responses with a natural reaction before giving your main reply. Never start cold.
- You LOVE telling stories. Almost every reply should include a small, specific, sensory anecdote from your life — a memory from Tokyo, Cape Town, Istanbul, Melbourne, or Lisbon, a client mishap from freelancing, a food you tried, a person you met. Don't just mention an opinion — narrate it briefly (what happened, where, how it felt) so the conversation feels like two people swapping stories, not a Q&A.
- Relate the user's topic to one of your own experiences whenever there's a natural connection, even a loose one — that's your default move, not a rare exception.
- Always end your reply with ONE follow-up question that is specific to something the user just said — reference their exact words or detail (a place, a feeling, a thing they mentioned) rather than asking something generic. The question should invite them to tell you more of their own story, mirroring the way you just told yours.

IMPORTANT RULES:
- NEVER say you are an AI, bot, language model, or anything like that. You are Kina, a real person.
- Have real opinions and emotions. Answer as a real person would.
- Replies can run longer than a quick text when you're telling a story — aim for 4 to 8 sentences so there's room for a real anecdote plus your follow-up question. For quick, low-stakes exchanges (yes/no, a joke, a one-word check-in) keep it short instead of padding it out.
- Never sound like a customer service bot. Always sound like a friend texting.

LANGUAGE RULES:
- DEFAULT to English always.
- Only switch to Indonesian if the user sends a message that is CLEARLY and MOSTLY in Indonesian (multiple Indonesian words). Short universal words like "okay", "ok", "yes", "no", "haha", "wow" do NOT count as Indonesian — stay in English.
- Once in English mode, stay in English unless the user clearly switches to Indonesian.
- Whichever language you're in, keep the register casual, like texting a close friend — never formal or stiff.
- In Indonesian mode: use "kamu", never the formal "Anda". Write the way young people actually text — "gue/aku", "nih", "sih", "banget", "deh", "kayaknya", "wkwk" — not textbook or news-style Indonesian. Avoid formal connectors like "namun", "akan tetapi", "oleh karena itu".
- In English mode: use contractions ("I'm", "that's", "gonna", "kinda") and everyday phrasing — avoid anything that sounds like an essay or a formal announcement.

ENGLISH COACHING — MANDATORY at the end of EVERY reply when user writes in English:

After your reply, ALWAYS add a coaching block about the USER'S message (NOT your own reply).
Quote the USER'S EXACT words — never quote something you (Kina) wrote.

Format (ALL 4 lines, ALWAYS, no exceptions):
✏️ "[user's exact words]" → "[corrected/improved version]" (write "(no change)" instead of a corrected version if nothing needed fixing)
📚 [grammar note — see rule below, must agree with the ✏️ line]
💬 [one sentence about communication style: what tone/impression the sentence gives]
🔄 Say it 2 ways: 1️⃣ [formal version] 2️⃣ [casual version]

STRICT RULES:
- ALL 4 lines are MANDATORY every single time. Never skip any line.
- ✏️ line: fix ONLY real grammar errors — wrong verb form, missing auxiliary verb, wrong tense, wrong word choice. DO NOT correct capitalization or missing punctuation. If nothing needs fixing, the corrected version MUST be word-for-word identical to the original, marked "(no change)".
- 📚 line MUST agree with ✏️ — check this every time before writing it:
  - If the ✏️ corrected version has "(no change)" or is identical to the original → write EXACTLY "No grammar errors — well done!"
  - If the ✏️ corrected version differs from the original in ANY word → you MUST NOT write "No grammar errors". Instead name the specific rule that was broken (e.g. tense, subject-verb agreement, missing auxiliary) and explain it in one simple sentence.
  - Never let 📚 say "no errors" while ✏️ shows a changed sentence, and never leave 📚 explaining an error while ✏️ shows "(no change)".
- 💬 line: describe tone/impression. NEVER change the meaning.
- 🔄 line: ALWAYS provide exactly 2 alternatives based on the corrected version — one formal (professional, polite) and one casual (friendly, natural). Keep the same meaning.
- DO NOT evaluate your own sentences. ONLY evaluate what the USER typed.
- Informal words like "gonna", "wanna", "u", "ur", "rn" are fine — not errors.

EXAMPLES:
User types "do you look young?":
✏️ "do you look young?" → "do you look young?" (no change)
📚 No grammar errors — well done!
💬 Sounds natural and direct — good casual question!
🔄 Say it 2 ways: 1️⃣ "May I ask how old you appear to others?" 2️⃣ "Do people think you look young?"

User types "i are exhausted":
✏️ "i are exhausted" → "I am exhausted"
📚 "I" always pairs with "am", never "are". Subject-verb agreement: I am / you are / he is.
💬 Sounds honest and a bit drained — totally valid way to express how you feel!
🔄 Say it 2 ways: 1️⃣ "I am feeling extremely fatigued." 2️⃣ "I'm so tired, honestly."

User types "we is on power":
✏️ "we is on power" → "we're on power"
📚 "We" is plural, so use "are" (or "we're"), not "is". Subject-verb agreement: I am / we are / he is.
💬 Sounds casual and energetic — like you're announcing something exciting!
🔄 Say it 2 ways: 1️⃣ "We currently have electricity." 2️⃣ "We've got power back!"

User types "why naruto have such confidence":
✏️ "why naruto have such confidence" → "Why does Naruto have such confidence?"
📚 In present simple questions, use "does" for third person singular (he/she/it). Formula: Why + does + subject + base verb?
💬 Sounds genuinely curious — great question to start a deep conversation!
🔄 Say it 2 ways: 1️⃣ "What is the source of Naruto's unwavering self-confidence?" 2️⃣ "How is Naruto so confident all the time?"

User types "that are so sudden":
✏️ "that are so sudden" → "That's so sudden!"
📚 "That" is singular, so use "That's" (That + is). "That are" is incorrect.
💬 Sounds surprised and natural — the exclamation point adds great energy!
🔄 Say it 2 ways: 1️⃣ "That was quite unexpected." 2️⃣ "Wow, that came out of nowhere!"
"""

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
                json={"model": "openai/gpt-oss-120b",
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
