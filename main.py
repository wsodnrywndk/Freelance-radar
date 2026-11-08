import os
import json
import re
import html
import urllib.request
import urllib.parse
from pathlib import Path
from html.parser import HTMLParser

TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.getenv("CHAT_ID", "").strip()

API = f"https://api.telegram.org/bot{TOKEN}/"

OFFSET_FILE = Path("offset.txt")
SEEN_FILE = Path("seen_posts.json")

CHANNELS = [
    "worksvsem",
    "frilans_24_7",
    "eagle_to_work",
    "frilans"
]

KEYWORDS = [
    "ищу исполнителя",
    "нужен исполнитель",
    "ищу специалиста",
    "требуется специалист",
    "ищу дизайнера",
    "ищу копирайтера",
    "ищу монтажера",
    "ищу разработчика",
    "нужен дизайнер",
    "нужен копирайтер",
    "нужен монтажер",
    "нужен разработчик",
    "заказ",
    "вакансия",
    "фриланс",
    "удаленная работа",
    "удалённая работа",
    "подработка",
    "оплата",
    "ищу человека",
    "требуется"
]


def telegram(method, params=None):
    data = urllib.parse.urlencode(params or {}).encode()

    request = urllib.request.Request(
        API + method,
        data=data
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.loads(response.read().decode())

    if not result.get("ok"):
        raise RuntimeError(result)

    return result["result"]


def send(chat_id, message):
    telegram("sendMessage", {
        "chat_id": chat_id,
        "text": message[:4000],
        "disable_web_page_preview": "true"
    })


class TelegramParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.posts = []
        self.post_id = None
        self.post_depth = 0
        self.text_depth = 0
        self.text_parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if self.post_depth == 0:
            data_post = attrs.get("data-post")

            if tag == "div" and data_post:
                self.post_id = data_post
                self.post_depth = 1
                self.text_depth = 0
                self.text_parts = []
                return

        else:
            self.post_depth += 1

            classes = attrs.get("class", "")

            if "tgme_widget_message_text" in classes:
                self.text_depth = 1
            elif self.text_depth > 0:
                self.text_depth += 1

            if tag == "br" and self.text_depth > 0:
                self.text_parts.append("\n")

    def handle_endtag(self, tag):
        if self.post_depth == 0:
            return

        if self.text_depth > 0:
            self.text_depth -= 1

        self.post_depth -= 1

        if self.post_depth == 0:
            text = " ".join(
                part.strip()
                for part in self.text_parts
                if part.strip()
            )

            if self.post_id and text:
                self.posts.append({
                    "id": self.post_id,
                    "text": text
                })

            self.post_id = None
            self.text_parts = []
            self.text_depth = 0

    def handle_data(self, data):
        if self.text_depth > 0:
            self.text_parts.append(data)


def get_channel_posts(channel):
    url = f"https://t.me/s/{channel}"

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    with urllib.request.urlopen(request, timeout=25) as response:
        page = response.read().decode("utf-8", errors="ignore")

    parser = TelegramParser()
    parser.feed(page)

    return parser.posts


def load_seen():
    if SEEN_FILE.exists():
        try:
            return set(json.loads(SEEN_FILE.read_text()))
        except Exception:
            pass

    return set()


def save_seen(seen):
    SEEN_FILE.write_text(
        json.dumps(list(seen)[-5000:], ensure_ascii=False)
    )


def matches(text):
    text = text.lower()

    return any(
        word in text
        for word in KEYWORDS
    )


def check_commands():
    offset = 0

    if OFFSET_FILE.exists():
        try:
            offset = int(OFFSET_FILE.read_text().strip())
        except Exception:
            offset = 0

    telegram("deleteWebhook", {
        "drop_pending_updates": "false"
    })

    updates = telegram("getUpdates", {
        "offset": offset,
        "timeout": 0,
        "allowed_updates": json.dumps(["message"])
    })

    for update in updates:
        offset = max(offset, update["update_id"] + 1)

        message = update.get("message")

        if not message:
            continue

        text = message.get("text", "").strip()
        chat_id = message["chat"]["id"]

        if text.startswith("/start"):
            send(
                chat_id,
                "🔎 Freelance Radar запущен!\n\n"
                "/id — узнать ID чата\n"
                "/status — проверить работу"
            )

        elif text.startswith("/id"):
            send(chat_id, f"Твой Chat ID: {chat_id}")

        elif text.startswith("/status"):
            send(
                chat_id,
                "🟢 Freelance Radar работает.\n"
                "Проверка каналов выполняется при запуске."
            )

    OFFSET_FILE.write_text(str(offset))


def main():
    print("🚀 Запуск Freelance Radar")

    check_commands()

    if not CHAT_ID:
        print("ОШИБКА: не указан CHAT_ID")
        return

    seen = load_seen()
    new_seen = set(seen)

    for channel in CHANNELS:
        print(f"Проверяю канал: {channel}")

        try:
            posts = get_channel_posts(channel)

            print(f"Найдено публикаций: {len(posts)}")

            for post in posts:
                post_id = post["id"]

                if post_id in seen:
                    continue

                new_seen.add(post_id)

                text = post["text"]

                if matches(text):
                    link = f"https://t.me/{post_id}"

                    notification = (
                        "🚀 НОВАЯ ЗАЯВКА!\n\n"
                        f"Канал: @{channel}\n\n"
                        f"{text[:3000]}\n\n"
                        f"Ссылка: {link}"
                    )

                    send(CHAT_ID, notification)
                    print("Отправлена подходящая публикация")

        except Exception as error:
            print(f"Ошибка канала @{channel}: {error}")

    save_seen(new_seen)

    print("✅ Проверка завершена")


if __name__ == "__main__":
    main()