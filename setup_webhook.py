import os
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.environ.get("TELEGRAM_TOKEN") or input("Masukkan TELEGRAM_TOKEN: ").strip()
WEBHOOK_URL = "https://kentmiracle-telegram-bot.hf.space/webhook"

r = requests.get(f"https://api.telegram.org/bot{TOKEN}/setWebhook",
                 params={"url": WEBHOOK_URL, "allowed_updates": '["message"]'})
print(r.json())

r2 = requests.get(f"https://api.telegram.org/bot{TOKEN}/getWebhookInfo")
print(r2.json())
