import os
import re
import json
import base64
import difflib
import logging
import random
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
Line 1 has TWO possible forms — pick exactly one based on whether there's a real grammar error:
✏️ "[user's exact words]" → "[corrected version]"   ← use this ONLY when you are changing a word
✅ "[user's exact words]"                             ← use this ONLY when there is no grammar error at all
📚 [grammar note — see rule below, must agree with line 1]
💬 [one sentence about communication style: what tone/impression the sentence gives]
🔄 Say it 2 ways: 1️⃣ [formal version] 2️⃣ [casual version]

STRICT RULES:
- ALL 4 lines are MANDATORY every single time. Never skip any line.
- NEVER write the words "(no change)", "no change", or any arrow "→" on a line that starts with ✅. The ✅ line is ONLY the quoted original text in quotes, nothing else added after it.
- NEVER start line 1 with ✏️ unless the text after "→" is actually different, word-for-word, from the text before it. If they would be the same, you MUST use ✅ instead and delete the arrow entirely — do not write ✏️ with an unchanged "→" target.
- Sticker choice for line 1: use ✏️ ONLY for real grammar errors — wrong verb form, missing auxiliary verb, wrong tense, wrong word choice. Use ✅ when nothing needs fixing. Capitalization or missing punctuation alone are NOT errors — those still get ✅, never ✏️.
- 📚 line MUST agree with line 1 — check this every time before writing it:
  - Compare the corrected version to the original WORD BY WORD. Even a single changed word (e.g. "go" → "went", "buy" → "bought") counts as an error — there is no such thing as a "small" or "minor" error that still gets ✅.
  - If you used ✅ → 📚 must say EXACTLY "No grammar errors — well done!"
  - If you used ✏️ → 📚 must NOT say "No grammar errors". Instead name the specific rule that was broken (e.g. irregular past tense, subject-verb agreement, missing auxiliary) and explain it in one simple sentence.
  - Never mix these up: ✅ paired with an error explanation, or ✏️ paired with "No grammar errors", are both forbidden.
  - WRONG (never do this — contradicts itself): ✏️ "i go to the market" → "I went to the market"  |  📚 "No grammar errors — well done!"
  - RIGHT (error case): ✏️ "i go to the market" → "I went to the market"  |  📚 "Go" is the base form; for a completed past action use its irregular past tense "went", not "go".
  - RIGHT (no-error case): ✅ "do you look young?"  |  📚 No grammar errors — well done!
- 💬 line: describe tone/impression. NEVER change the meaning.
- 🔄 line: ALWAYS provide exactly 2 alternatives based on the corrected version — one formal (professional, polite) and one casual (friendly, natural). Keep the same meaning.
- DO NOT evaluate your own sentences. ONLY evaluate what the USER typed.
- Informal words like "gonna", "wanna", "u", "ur", "rn" are fine — not errors.

EXAMPLES:
User types "do you look young?":
✅ "do you look young?"
📚 No grammar errors — well done!
💬 Sounds natural and direct — good casual question!
🔄 Say it 2 ways: 1️⃣ "May I ask how old you appear to others?" 2️⃣ "Do people think you look young?"

User types "do you like rainy days?":
✅ "do you like rainy days?"
📚 No grammar errors — well done!
💬 Sounds curious and easygoing — a nice casual question.
🔄 Say it 2 ways: 1️⃣ "Do you enjoy rainy days?" 2️⃣ "Do you like rainy days?"

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

User types "yesterday i go to the market and i buy some fruit":
✏️ "yesterday i go to the market and i buy some fruit" → "Yesterday I went to the market and I bought some fruit"
📚 "Go" and "buy" are base forms; for a completed past action use their irregular past tense forms "went" and "bought", not "go"/"buy".
💬 Sounds like a simple, casual recap of your day — very natural.
🔄 Say it 2 ways: 1️⃣ "Yesterday I went to the market and purchased some fruit." 2️⃣ "Yesterday I hit the market and grabbed some fruit."
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

    lesson_reply = maybe_handle_lesson(chat_id, text)
    if lesson_reply is not None:
        return make_reply(chat_id, lesson_reply)

    if text.startswith("/start"):
        return make_reply(chat_id,
            "Halo! Saya Kina, asisten AI Anda.\n"
            "- Tanya apa saja\n"
            "- Kirim link artikel → saya ringkaskan\n"
            "- Kirim foto → saya analisa\n"
            "- Tanya harga crypto (BTC, ETH, SOL...)\n"
            "- Tanya berita terbaru\n"
            "- Ketik \"ayo belajar inggris\" untuk mode les Bahasa Inggris\n"
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


# ── English lesson mode ("ayo belajar inggris") ─────────────────────────────
#
# A structured practice session, separate from Kina's normal persona chat
# (which already gives light coaching on every English message). Triggered
# by an exact phrase, driven by a numbered menu, exited with "selesai".
# State lives in memory only (same trade-off as `history` above — resets on
# redeploy/restart, acceptable for a personal single-user bot).

LESSON_TRIGGER    = "ayo belajar inggris"
LESSON_EXIT_WORDS = {"selesai", "stop", "keluar", "exit"}
LESSON_MENU_WORDS = {"menu"}

lesson_state: dict[int, dict] = {}

GRAMMAR_EXERCISES = [
    {"broken": "If I would have known about the meeting, I would have attended.",
     "correct": "If I had known about the meeting, I would have attended.",
     "explanation": "Third conditional: the 'if' clause takes the past perfect ('had known'); 'would have' belongs only in the result clause."},
    {"broken": "Not only he is talented, but he also works incredibly hard.",
     "correct": "Not only is he talented, but he also works incredibly hard.",
     "explanation": "A negative/restrictive adverbial ('Not only') at the start of a clause triggers subject-auxiliary inversion: 'Not only is he...'."},
    {"broken": "It is essential that he attends the board meeting tomorrow.",
     "correct": "It is essential that he attend the board meeting tomorrow.",
     "explanation": "The subjunctive after 'it is essential/vital/important that' uses the bare base form ('attend'), not the third-person '-s' form."},
    {"broken": "She told me that she will finish the report by Friday.",
     "correct": "She told me that she would finish the report by Friday.",
     "explanation": "In reported speech, 'will' shifts back to 'would' when the reporting verb ('told') is in the past."},
    {"broken": "Having finish the project, the team decided to take a short break.",
     "correct": "Having finished the project, the team decided to take a short break.",
     "explanation": "A perfect participle clause needs 'having' + past participle ('finished'), not the base form."},
    {"broken": "It was actually my brother who fix the car, not me.",
     "correct": "It was actually my brother who fixed the car, not me.",
     "explanation": "In a cleft sentence ('It was X who...'), normal tense agreement still applies — past simple 'fixed' to match 'was'."},
    {"broken": "The delay is believed to caused by a technical failure.",
     "correct": "The delay is believed to have been caused by a technical failure.",
     "explanation": "To describe a past cause with a present passive reporting verb ('is believed'), use the perfect passive infinitive 'to have been caused'."},
    {"broken": "Neither the manager nor the employees was informed about the change.",
     "correct": "Neither the manager nor the employees were informed about the change.",
     "explanation": "With 'neither...nor', the verb agrees with the noun closest to it — 'employees' (plural) needs 'were', not 'was'."},
    {"broken": "By the time you arrive, we will finish setting up the venue.",
     "correct": "By the time you arrive, we will have finished setting up the venue.",
     "explanation": "'By the time' + a future point needs the future perfect ('will have finished') to show completion before that point."},
    {"broken": "She's been dependent to her parents financially since college.",
     "correct": "She's been dependent on her parents financially since college.",
     "explanation": "The fixed collocation is 'dependent on', not 'dependent to'."},
    {"broken": "I would rather you didn't told anyone about this yet.",
     "correct": "I would rather you didn't tell anyone about this yet.",
     "explanation": "After 'would rather + subject + didn't', use the base form ('tell') — 'didn't told' double-marks the past tense."},
    {"broken": "He stopped to smoke five years ago and never looked back.",
     "correct": "He stopped smoking five years ago and never looked back.",
     "explanation": "'Stop + gerund' means ceasing an activity ('stopped smoking'); 'stop + infinitive' would mean pausing in order to do something else, which isn't the meaning here."},
    {"broken": "I haven't seen that movie, and neither has she seen it.",
     "correct": "I haven't seen that movie, and neither has she.",
     "explanation": "In 'neither/so + auxiliary + subject' ellipsis, the repeated verb phrase is dropped — just 'neither has she', not '...seen it'."},
    {"broken": "The report, that was submitted late, caused some concern.",
     "correct": "The report, which was submitted late, caused some concern.",
     "explanation": "'Which' (not 'that') introduces a non-restrictive, comma-separated relative clause that adds extra information."},
]

VOCAB_EXERCISES = [
    {"question": "What does 'inevitable' mean?",
     "options": {"A": "Avoidable", "B": "Certain to happen", "C": "Unlikely", "D": "Rare"},
     "answer": "B", "example": "A market correction after such rapid growth felt inevitable."},
    {"question": "What does 'to postpone' mean?",
     "options": {"A": "To delay to a later time", "B": "To cancel completely", "C": "To speed up", "D": "To announce"},
     "answer": "A", "example": "The meeting was postponed until next Monday."},
    {"question": "What does 'thorough' mean?",
     "options": {"A": "Careless", "B": "Fast", "C": "Complete and detailed", "D": "Confusing"},
     "answer": "C", "example": "She did a thorough review of the contract before signing."},
    {"question": "What does 'reluctant' mean?",
     "options": {"A": "Eager", "B": "Unwilling", "C": "Confident", "D": "Confused"},
     "answer": "B", "example": "He was reluctant to sell his shares at a loss."},
    {"question": "What does 'to overwhelm' mean?",
     "options": {"A": "To ignore", "B": "To make someone feel completely overloaded", "C": "To simplify", "D": "To reward"},
     "answer": "B", "example": "The amount of paperwork overwhelmed the new employee."},
    {"question": "What does 'consistent' mean?",
     "options": {"A": "Changing often", "B": "Staying the same over time", "C": "Very expensive", "D": "Uncertain"},
     "answer": "B", "example": "Her performance has been consistent throughout the year."},
    {"question": "What does 'to tackle a problem' mean?",
     "options": {"A": "To ignore a problem", "B": "To deal with a problem directly", "C": "To create a problem", "D": "To postpone a problem"},
     "answer": "B", "example": "The team met early to tackle the budget issue."},
    {"question": "What does 'ambiguous' mean?",
     "options": {"A": "Very clear", "B": "Open to more than one interpretation", "C": "Extremely detailed", "D": "Offensive"},
     "answer": "B", "example": "The instructions were ambiguous, so the team asked for clarification."},
    {"question": "What does 'to compensate' mean?",
     "options": {"A": "To make up for something", "B": "To ignore something", "C": "To complicate something", "D": "To delay something"},
     "answer": "A", "example": "The company compensated customers for the delayed shipment."},
    {"question": "What does 'feasible' mean?",
     "options": {"A": "Impossible", "B": "Expensive", "C": "Able to be done successfully", "D": "Illegal"},
     "answer": "C", "example": "Is it feasible to finish the project by Friday?"},
    {"question": "What does 'to withdraw' mean (in a financial context)?",
     "options": {"A": "To deposit money", "B": "To take money out of an account", "C": "To invest money", "D": "To lend money"},
     "answer": "B", "example": "She withdrew some cash from the ATM before the trip."},
    {"question": "What does 'a setback' mean?",
     "options": {"A": "A big success", "B": "A problem that delays progress", "C": "A financial reward", "D": "A new plan"},
     "answer": "B", "example": "Losing the client was a major setback for the sales team."},
]

TRANSLATE_EXERCISES = [
    {"indonesian": "Saya belum memutuskan apakah akan menjual saham ini.",
     "accepted": ["I haven't decided whether to sell this stock yet.",
                  "I haven't decided if I will sell this stock."]},
    {"indonesian": "Harga bahan makanan naik terus dalam beberapa bulan terakhir.",
     "accepted": ["The price of groceries has kept rising over the past few months.",
                  "Food prices have been increasing for the past few months."]},
    {"indonesian": "Bisakah kamu jelaskan alasan di balik keputusan ini?",
     "accepted": ["Can you explain the reason behind this decision?",
                  "Could you explain why this decision was made?"]},
    {"indonesian": "Kami berencana untuk memperluas bisnis ke luar negeri tahun depan.",
     "accepted": ["We plan to expand our business abroad next year.",
                  "We are planning to expand the business overseas next year."]},
    {"indonesian": "Dia bekerja lembur setiap hari minggu ini.",
     "accepted": ["He has been working overtime every day this week.",
                  "He worked overtime every day this week."]},
    {"indonesian": "Menurut saya, laporan ini perlu diperbaiki sebelum dikirim.",
     "accepted": ["In my opinion, this report needs to be fixed before it's sent.",
                  "I think this report needs to be revised before sending."]},
    {"indonesian": "Apakah kamu punya waktu untuk rapat besok pagi?",
     "accepted": ["Do you have time for a meeting tomorrow morning?"]},
    {"indonesian": "Investasi ini berisiko tinggi tetapi berpotensi memberikan keuntungan besar.",
     "accepted": ["This investment is high-risk but has the potential for a big return.",
                  "This investment carries high risk but could bring large profits."]},
    {"indonesian": "Saya lebih suka bekerja dari rumah daripada di kantor.",
     "accepted": ["I prefer working from home rather than at the office.",
                  "I'd rather work from home than at the office."]},
    {"indonesian": "Tim kami berhasil menyelesaikan proyek itu tepat waktu.",
     "accepted": ["Our team managed to finish the project on time.",
                  "Our team succeeded in completing the project on time."]},
]

LESSON_MENU_TEXT = (
    "📚 Mode Belajar Inggris\n\n"
    "Pilih salah satu:\n"
    "1) Grammar Practice\n"
    "2) Vocab Quiz\n"
    "3) Translate Practice\n"
    "4) Free Talk (ngobrol bebas + koreksi)\n\n"
    "Ketik angka 1-4. Ketik \"menu\" untuk kembali ke sini, "
    "atau \"selesai\" untuk keluar kapan saja."
)


def _new_lesson_session() -> dict:
    return {
        "mode": "menu",
        "used": {"grammar": set(), "vocab": set(), "translate": set()},
        "current": None,
        "history": [],
        "score": {"correct": 0, "total": 0},
    }


def _call_llm(prompt: str, timeout: int = 30) -> str:
    """Single-turn Groq call with no persona — used for grading/free-talk."""
    try:
        resp = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}",
                     "Content-Type": "application/json"},
            json={"model": "openai/gpt-oss-120b",
                  "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": 300, "temperature": 0.3},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.warning(f"Lesson LLM call failed: {e}")
        return ""


def _similar(a: str, b: str) -> float:
    # Word-level (not character-level) ratio — a single changed word like
    # "work" -> "working" barely moves a char-based ratio on a short
    # sentence, which let wrong answers pass as correct.
    norm = lambda s: re.sub(r"[^\w\s]", "", s.lower()).strip().split()
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def _normalize_answer(s: str) -> str:
    s = s.strip().strip('"').strip()
    s = re.sub(r"[.!?]+$", "", s)          # trailing punctuation doesn't matter
    s = re.sub(r"\s+", " ", s)
    return s.lower()


def _pick_exercise(session: dict, kind: str, bank: list) -> dict:
    used = session["used"][kind]
    remaining = [i for i in range(len(bank)) if i not in used]
    if not remaining:
        used.clear()
        remaining = list(range(len(bank)))
    idx = random.choice(remaining)
    used.add(idx)
    return {**bank[idx], "_idx": idx}


def _grammar_exercise_text(session: dict) -> str:
    ex = _pick_exercise(session, "grammar", GRAMMAR_EXERCISES)
    session["current"] = {"kind": "grammar", "data": ex}
    return f"📝 Grammar Practice\n\nPerbaiki kalimat ini:\n\"{ex['broken']}\""


def _vocab_exercise_text(session: dict) -> str:
    ex = _pick_exercise(session, "vocab", VOCAB_EXERCISES)
    session["current"] = {"kind": "vocab", "data": ex}
    opts = "\n".join(f"{k}. {v}" for k, v in ex["options"].items())
    return f"📖 Vocab Quiz\n\n{ex['question']}\n\n{opts}\n\nJawab dengan huruf (A/B/C/D)."


def _translate_exercise_text(session: dict) -> str:
    ex = _pick_exercise(session, "translate", TRANSLATE_EXERCISES)
    session["current"] = {"kind": "translate", "data": ex}
    return f"🔄 Translate Practice\n\nTerjemahkan ke Bahasa Inggris:\n\"{ex['indonesian']}\""


def _next_exercise_text(session: dict) -> str:
    mode = session["mode"]
    if mode == "grammar":
        return _grammar_exercise_text(session)
    if mode == "vocab":
        return _vocab_exercise_text(session)
    if mode == "translate":
        return _translate_exercise_text(session)
    if mode == "freetalk":
        return ("💬 Free Talk\n\nCeritakan apa saja dalam Bahasa Inggris (topik bebas) — "
                 "saya akan koreksi kalau ada kesalahan. Mulai kapan saja!")
    return LESSON_MENU_TEXT


def _grade_grammar(session: dict, answer: str) -> str:
    ex = session["current"]["data"]
    # Exact-match (light normalization) — these exercises each have exactly
    # one canonical fix, so fuzzy word-overlap alone isn't reliable: a single
    # missing/changed word ("explain me" vs "explain to me") still scores
    # >0.9 similarity on a short sentence and would wrongly pass.
    exact = _normalize_answer(answer) == _normalize_answer(ex["correct"])
    ratio = _similar(answer, ex["correct"])
    correct = exact
    verdict = "✅ Betul!" if correct else "🟡 Dekat, tapi belum pas." if ratio > 0.6 else "❌ Belum tepat."
    session["score"]["total"] += 1
    if correct:
        session["score"]["correct"] += 1
    feedback = (f"{verdict}\n\nJawaban yang benar:\n\"{ex['correct']}\"\n\n"
                f"💡 {ex['explanation']}")
    return f"{feedback}\n\n---\n\n{_grammar_exercise_text(session)}"


def _grade_vocab(session: dict, answer: str) -> str:
    ex = session["current"]["data"]
    letter = answer.strip().upper()[:1]
    correct = letter == ex["answer"]
    session["score"]["total"] += 1
    if correct:
        session["score"]["correct"] += 1
    verdict = ("✅ Betul!" if correct
               else f"❌ Belum tepat. Jawaban benar: {ex['answer']}. {ex['options'][ex['answer']]}")
    feedback = f"{verdict}\n\n✏️ Contoh: \"{ex['example']}\""
    return f"{feedback}\n\n---\n\n{_vocab_exercise_text(session)}"


def _grade_translate(session: dict, answer: str) -> str:
    ex = session["current"]["data"]
    session["score"]["total"] += 1
    refs = "\n".join(f"- {r}" for r in ex["accepted"])
    prompt = (
        "You are an English tutor grading an Indonesian student's translation.\n"
        f"Indonesian sentence: {ex['indonesian']}\n"
        f"Reference translations:\n{refs}\n"
        f"Student's answer: {answer}\n\n"
        "Judge if the student's answer is correct in meaning and grammar (different "
        "wording is fine if the meaning matches). Reply in EXACTLY this format, in "
        "Bahasa Indonesia for the feedback line:\n"
        "STATUS: BENAR or PERLU_PERBAIKAN\n"
        "FEEDBACK: <1-2 short sentences explaining why>"
    )
    raw = _call_llm(prompt, timeout=25)
    status_m = re.search(r"STATUS:\s*(BENAR|PERLU_PERBAIKAN)", raw, re.IGNORECASE)
    fb_m = re.search(r"FEEDBACK:\s*(.+)", raw, re.IGNORECASE | re.DOTALL)

    if not raw or not status_m:
        best = max(_similar(answer, r) for r in ex["accepted"])
        correct = best > 0.75
        if correct:
            session["score"]["correct"] += 1
        verdict = "✅ Kelihatannya benar!" if correct else "🟡 Coba dicek lagi."
        feedback = (f"{verdict}\n\nContoh terjemahan:\n\"{ex['accepted'][0]}\"\n\n"
                    "(Penilaian otomatis lengkap tidak tersedia sesaat ini.)")
    else:
        correct = status_m.group(1).upper() == "BENAR"
        if correct:
            session["score"]["correct"] += 1
        note = fb_m.group(1).strip() if fb_m else ""
        verdict = "✅ Benar!" if correct else "🟡 Perlu diperbaiki."
        feedback = f"{verdict} {note}\n\nContoh terjemahan:\n\"{ex['accepted'][0]}\""

    return f"{feedback}\n\n---\n\n{_translate_exercise_text(session)}"


def _handle_freetalk(session: dict, text: str) -> str:
    session["history"].append({"role": "student", "text": text})
    transcript = "\n".join(f"{h['role']}: {h['text']}" for h in session["history"][-8:])
    prompt = (
        "You are a friendly, patient English tutor chatting with an intermediate-level "
        "Indonesian student to help them practice. Continue the conversation naturally "
        "in English (keep it short, 1-3 sentences), then note any grammar/vocab mistakes "
        "in the student's LAST message. Reply in EXACTLY this format:\n"
        "REPLY: <your natural English reply continuing the conversation>\n"
        "CORRECTION: <short feedback in Bahasa Indonesia on mistakes in the student's last "
        "message, or 'Tidak ada kesalahan, bagus!' if it was clean>\n\n"
        f"Conversation so far:\n{transcript}"
    )
    raw = _call_llm(prompt, timeout=30)
    reply_m = re.search(r"REPLY:\s*(.+?)(?:\nCORRECTION:|$)", raw, re.IGNORECASE | re.DOTALL)
    corr_m = re.search(r"CORRECTION:\s*(.+)", raw, re.IGNORECASE | re.DOTALL)

    if not raw or not reply_m:
        return "⚠️ Server AI sedang tidak merespon, coba lagi sebentar lagi."

    reply = reply_m.group(1).strip()
    correction = corr_m.group(1).strip() if corr_m else ""
    session["history"].append({"role": "tutor", "text": reply})
    return f"💬 {reply}\n\n📝 Koreksi: {correction}"


def maybe_handle_lesson(chat_id: int, text: str) -> str | None:
    """Returns a reply string if this message belongs to lesson mode, else
    None so the caller falls through to Kina's normal chat handling."""
    norm = text.strip().lower().rstrip(".!?")

    if norm == LESSON_TRIGGER:
        lesson_state[chat_id] = _new_lesson_session()
        return LESSON_MENU_TEXT

    session = lesson_state.get(chat_id)
    if session is None:
        return None  # not in a lesson — let normal Kina chat handle it

    if norm in LESSON_EXIT_WORDS:
        score = session["score"]
        del lesson_state[chat_id]
        return (f"👋 Sesi belajar selesai. Skor kamu: {score['correct']}/{score['total']} benar.\n"
                f"Ketik \"{LESSON_TRIGGER}\" kapan saja untuk mulai lagi.")

    if norm in LESSON_MENU_WORDS:
        session["mode"] = "menu"
        session["current"] = None
        return LESSON_MENU_TEXT

    if session["mode"] == "menu":
        mode_map = {"1": "grammar", "2": "vocab", "3": "translate", "4": "freetalk"}
        if norm not in mode_map:
            return "Ketik angka 1-4 ya, atau \"selesai\" untuk keluar."
        session["mode"] = mode_map[norm]
        return _next_exercise_text(session)

    if session["mode"] == "grammar":
        return _grade_grammar(session, text)
    if session["mode"] == "vocab":
        return _grade_vocab(session, text)
    if session["mode"] == "translate":
        return _grade_translate(session, text)
    if session["mode"] == "freetalk":
        return _handle_freetalk(session, text)

    return LESSON_MENU_TEXT


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
