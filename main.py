import os
import json
import re
import urllib.request
import urllib.parse
from pathlib import Path
from bs4 import BeautifulSoup

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

MAX_ALERTS_PER_RUN = 3


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
        "text": message[:4000],
        "disable_web_page_preview": "true"
    })


def load_seen():
    if SEEN_FILE.exists():
        try:
            return set(json.loads(SEEN_FILE.read_text()))
        except Exception:
            return set()
    return set()


def save_seen(seen):
    SEEN_FILE.write_text(
        json.dumps(sorted(seen)[-5000:], ensure_ascii=False)
    )


def get_channel_posts(channel):
    url = f"https://t.me/s/{channel}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )

    with urllib.request.urlopen(request, timeout=25) as response:
        page = response.read().decode("utf-8", errors="ignore")

    soup = BeautifulSoup(page, "html.parser")
    posts = []
    found = set()

    for block in soup.find_all(attrs={"data-post": True}):
        post_id = block.get("data-post")

        if not post_id or post_id in found:
            continue

        message = block.select_one(".tgme_widget_message_text")
        if not message:
            continue

        text = message.get_text("\n", strip=True)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()

        if not text:
            continue

        found.add(post_id)
        posts.append({
            "id": post_id,
            "text": text,
            "link": f"https://t.me/{post_id}"
        })

    return posts


def matches(text):
    text = text.lower()

    exclude = [
        "подписывайтесь",
        "розыгрыш",
        "вебинар",
        "обучение",
        "курс",
        "бесплатный марафон",
        "ищу работу",
        "ищу вакансию"
    ]

    if any(word in text for word in exclude):
        return False

    hiring_words = [
        "ищу исполнителя",
        "нужен исполнитель",
        "ищу специалиста",
        "требуется специалист",
        "ищу дизайнера",
        "нужен дизайнер",
        "ищу копирайтера",
        "ищу разработчика",
        "ищу монтажера",
        "ищу монтажёра",
        "ищу фрилансера",
        "ищем специалиста",
        "нужен человек",
        "ищу человека",
        "заказ на",
        "нужен подрядчик",
        "требуется дизайнер",
        "требуется разработчик"
    ]

    payment_words = [
        "₽",
        "руб",
        "оплата",
        "бюджет",
        "стоимость",
        "платно",
        "гонорар"
    ]

    return (
        any(word in text for word in hiring_words)
        and any(word in text for word in payment_words)
    )


def check_commands():
    offset = 0

    if OFFSET_FILE.exists():
        try:
            offset = int(OFFSET_FILE.read_text().strip())
        except Exception:
            offset = 0

    telegram("deleteWebhook", {"drop_pending_updates": "false"})

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

        command = message.get("text", "").strip()
        chat_id = message["chat"]["id"]

        if command.startswith("/start"):
            send(
                chat_id,
                "🔎 Freelance Radar запущен!\n\n"
                "/id — узнать ID чата\n"
                "/status — проверить работу"
            )
        elif command.startswith("/id"):
            send(chat_id, f"Твой Chat ID: {chat_id}")
        elif command.startswith("/status"):
            send(
                chat_id,
                "🟢 Freelance Radar работает.\n"
                "Проверка каналов выполняется при запуске."
            )

    OFFSET_FILE.write_text(str(offset))


def main():
    print("🚀 Freelance Radar запущен")

    check_commands()

    if not CHAT_ID:
        print("ОШИБКА: CHAT_ID не указан")
        return

    seen = load_seen()
    new_seen = set(seen)
    pending_posts = []

    for channel in CHANNELS:
        print(f"Проверка @{channel}")

        try:
            posts = get_channel_posts(channel)
            print(f"Найдено публикаций: {len(posts)}")

            for post in posts:
                post_id = post["id"]

                if post_id in seen:
                    continue

                if matches(post["text"]):
                    pending_posts.append((channel, post))
                else:
                    new_seen.add(post_id)

        except Exception as error:
            print(f"Ошибка @{channel}: {error}")

    sent_count = 0

    for channel, post in pending_posts[:MAX_ALERTS_PER_RUN]:
        notification = (
            "🚀 НОВЫЙ ЗАКАЗ\n"
            "━━━━━━━━━━━━━━\n\n"
            f"📢 Канал: @{channel}\n\n"
            "📝 Описание:\n"
            f"{post['text']}\n\n"
            "━━━━━━━━━━━━━━\n"
            f"🔗 Открыть оригинал:\n{post['link']}"
        )

        send(CHAT_ID, notification)
        new_seen.add(post["id"])
        sent_count += 1
        print(f"Отправлен заказ из @{channel}")

    print(f"Отправлено заказов: {sent_count}")
    save_seen(new_seen)
    print("✅ Проверка завершена")


if __name__ == "__main__":
    main()