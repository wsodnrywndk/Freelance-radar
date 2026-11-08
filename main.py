
import json
import os
import urllib.parse
import urllib.request
import html
from pathlib import Path

TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.getenv("CHAT_ID", "").strip()
API = f"https://api.telegram.org/bot{TOKEN}/"
OFFSET_FILE = Path("offset.txt")

KEYWORDS = [
    "ищу исполнителя", "нужен исполнитель",
    "ищу специалиста", "требуется специалист",
    "заказ", "вакансия", "фриланс",
    "разработка сайта", "дизайн",
    "инфографика", "монтаж", "копирайтинг"
]


def telegram(method, params=None):
    data = urllib.parse.urlencode(params or {}).encode()
    request = urllib.request.Request(API + method, data=data)
    with urllib.request.urlopen(request, timeout=25) as response:
        result = json.loads(response.read().decode())

    if not result.get("ok"):
        raise RuntimeError(result)

    return result["result"]


def send(chat_id, text):
    telegram("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": "true"
    })


def get_link(post):
    chat = post["chat"]
    username = chat.get("username")

    if username:
        return f"https://t.me/{username}/{post['message_id']}"

    chat_id = str(chat["id"])
    if chat_id.startswith("-100"):
        return f"https://t.me/c/{chat_id[4:]}/{post['message_id']}"

    return ""


def main():
    offset = 0
    if OFFSET_FILE.exists():
        try:
            offset = int(OFFSET_FILE.read_text().strip())
        except ValueError:
            offset = 0

    telegram("deleteWebhook", {"drop_pending_updates": "false"})

    updates = telegram("getUpdates", {
        "offset": offset,
        "timeout": 0,
        "allowed_updates": json.dumps(["message", "channel_post"])
    })

    for update in updates:
        offset = max(offset, update["update_id"] + 1)

        message = update.get("message")
        if message:
            text = message.get("text", "")
            chat_id = message["chat"]["id"]

            if text.startswith("/start"):
                send(chat_id, "🔎 Freelance Radar работает! Напиши /id, чтобы узнать свой ID чата.")
            elif text.startswith("/id"):
                send(chat_id, f"Твой Chat ID: {chat_id}")
            elif text.startswith("/status"):
                send(chat_id, "🟢 Парсер готов к работе.")

        post = update.get("channel_post")
        if post:
            text = post.get("text") or post.get("caption") or ""

            if text and any(word in text.lower() for word in KEYWORDS):
                if CHAT_ID:
                    link = get_link(post)
                    safe_text = html.escape(text[:3000])
                    notification = "🚀 НОВАЯ ЗАЯВКА!\n\n" + safe_text

                    if link:
                        notification += "\n\n" + link

                    send(CHAT_ID, notification)

    OFFSET_FILE.write_text(str(offset))


if __name__ == "__main__":
    main()
