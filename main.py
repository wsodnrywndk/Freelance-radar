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
    "ищу исполнителя",
    "нужен исполнитель",
    "ищу специалиста",
    "требуется специалист",
    "заказ",
    "вакансия",
    "фриланс",
    "разработка сайта",
    "дизайн",
    "инфографика",
    "монтаж",
    "копирайтинг"
]


def telegram(method, params=None):
    data = urllib.parse.urlencode(params or {}).encode()
    request = urllib.request.Request(API + method, data=data)

    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.loads(response.read().decode())

    if not result.get("ok"):
        raise RuntimeError(result)

    return result["result"]


def send(chat_id, message):
    telegram("sendMessage", {
        "chat_id": chat_id,
        "text": message,
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
        except (ValueError, OSError):
            offset = 0

    print("Запуск Freelance Radar...")
    print("Текущий offset:", offset)

    telegram("deleteWebhook", {
        "drop_pending_updates": "false"
    })

    updates = telegram("getUpdates", {
        "offset": offset,
        "timeout": 20,
        "allowed_updates": json.dumps([
            "message",
            "channel_post"
        ])
    })

    print("Получено обновлений:", len(updates))

    for update in updates:
        offset = max(offset, update["update_id"] + 1)

        message = update.get("message")

        if message:
            text = message.get("text", "").strip()
            chat_id = message["chat"]["id"]

            print("Получено сообщение:", text)

            if text.startswith("/start"):
                send(
                    chat_id,
                    "🔎 Freelance Radar запущен!\n\n"
                    "Команды:\n"
                    "/id — узнать ID чата\n"
                    "/status — проверить работу"
                )

            elif text.startswith("/id"):
                send(chat_id, f"Твой Chat ID: {chat_id}")

            elif text.startswith("/status"):
                send(
                    chat_id,
                    "🟢 Freelance Radar работает.\n"
                    "Последняя проверка выполнена."
                )

        post = update.get("channel_post")

        if post:
            post_text = post.get("text") or post.get("caption") or ""

            if post_text and any(
                word in post_text.lower()
                for word in KEYWORDS
            ):
                if CHAT_ID:
                    link = get_link(post)
                    notification = (
                        "🚀 НОВАЯ ЗАЯВКА!\n\n"
                        + html.escape(post_text[:3000])
                    )

                    if link:
                        notification += "\n\n" + link

                    send(CHAT_ID, notification)

    OFFSET_FILE.write_text(str(offset))
    print("Новый offset сохранён:", offset)
    print("Работа завершена.")


if __name__ == "__main__":
    main()