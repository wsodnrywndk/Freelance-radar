import os
import json
import re
import urllib.request
import urllib.parse
import uuid
from pathlib import Path
from bs4 import BeautifulSoup

TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.getenv("CHAT_ID", "").strip()
API = f"https://api.telegram.org/bot{TOKEN}/"

OFFSET_FILE = Path("offset.txt")
SEEN_FILE = Path("seen_posts.json")
ORDERS_FILE = Path("orders.json")
CARD_FILE = Path("order_card.png")

CHANNELS = ["worksvsem", "frilans_24_7", "eagle_to_work", "frilans"]
MAX_ALERTS_PER_RUN = 3


def telegram(method, params=None):
    data = urllib.parse.urlencode(params or {}).encode()
    request = urllib.request.Request(API + method, data=data)
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.loads(response.read().decode())
    if not result.get("ok"):
        raise RuntimeError(result)
    return result["result"]


def send(chat_id, message, reply_markup=None):
    params = {
        "chat_id": chat_id,
        "text": message[:4000],
        "disable_web_page_preview": "true"
    }
    if reply_markup:
        params["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
    telegram("sendMessage", params)


def send_order_card(chat_id, channel, post, order_key):
    description = post["text"].strip()
    if len(description) > 650:
        description = description[:647].rsplit(" ", 1)[0] + "..."

    caption = (
        "НОВЫЙ ЗАКАЗ\n\n"
        f"Канал: @{channel}\n\n"
        f"Описание:\n{description}"
    )

    keyboard = {
        "inline_keyboard": [
            [{
                "text": "↗ Перейти к заказу",
                "url": post["link"]
            }],
            [{
                "text": "✍ Сгенерировать отклик",
                "callback_data": f"reply|{order_key}"
            }],
            [{
                "text": "Пропустить",
                "callback_data": f"skip|{order_key}"
            }]
        ]
    }

    if CARD_FILE.exists():
        boundary = "----FreelanceRadarBoundary" + uuid.uuid4().hex
        fields = {
            "chat_id": str(chat_id),
            "caption": caption[:1024],
            "reply_markup": json.dumps(keyboard, ensure_ascii=False)
        }
        body = bytearray()
        for name, value in fields.items():
            body.extend(f"--{boundary}\r\n".encode())
            body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
            body.extend(value.encode())
            body.extend(b"\r\n")

        body.extend(f"--{boundary}\r\n".encode())
        body.extend(
            f'Content-Disposition: form-data; name="photo"; filename="order_card.png"\r\n'.encode()
        )
        body.extend(b"Content-Type: image/png\r\n\r\n")
        body.extend(CARD_FILE.read_bytes())
        body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode())

        request = urllib.request.Request(
            API + "sendPhoto",
            data=bytes(body),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
        )
        with urllib.request.urlopen(request, timeout=45) as response:
            result = json.loads(response.read().decode())
        if not result.get("ok"):
            raise RuntimeError(result)
    else:
        send(chat_id, caption, keyboard)


def load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def load_seen():
    return set(load_json(SEEN_FILE, []))


def save_seen(seen):
    save_json(SEEN_FILE, sorted(seen)[-5000:])


def get_channel_posts(channel):
    url = f"https://t.me/s/{channel}"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=25) as response:
        page = response.read().decode("utf-8", errors="ignore")

    soup = BeautifulSoup(page, "html.parser")
    posts, found = [], set()

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
        "подписывайтесь", "розыгрыш", "вебинар", "обучение", "курс",
        "бесплатный марафон", "ищу работу", "ищу вакансию"
    ]
    if any(word in text for word in exclude):
        return False

    hiring_words = [
        "ищу исполнителя", "нужен исполнитель", "ищу специалиста",
        "требуется специалист", "ищу дизайнера", "нужен дизайнер",
        "ищу копирайтера", "ищу разработчика", "ищу монтажера",
        "ищу монтажёра", "ищу фрилансера", "ищем специалиста",
        "нужен человек", "ищу человека", "заказ на", "нужен подрядчик",
        "требуется дизайнер", "требуется разработчик"
    ]
    payment_words = ["₽", "руб", "оплата", "бюджет", "стоимость", "платно", "гонорар"]
    return any(w in text for w in hiring_words) and any(w in text for w in payment_words)


def make_reply(order):
    text = order.get("text", "").lower()
    if any(w in text for w in ["дизайн", "дизайнер", "карточ", "баннер", "логотип"]):
        task = "по вашему дизайн-проекту"
    elif any(w in text for w in ["сайт", "верстк", "разработ", "бот"]):
        task = "по вашей задаче"
    elif any(w in text for w in ["текст", "стать", "копирайт", "описан"]):
        task = "по подготовке текста"
    elif any(w in text for w in ["видео", "монтаж", "рилс", "reels"]):
        task = "по монтажу видео"
    else:
        task = "по вашему заказу"

    return (
        "Здравствуйте! Заинтересовал ваш заказ.\n\n"
        f"Готов обсудить детали и предложить решение {task}. "
        "Подскажите, пожалуйста, какие материалы и требования уже есть "
        "и какой результат вы ожидаете?\n\n"
        "Буду рад обсудить сроки и стоимость."
    )


def handle_callback(callback, orders):
    callback_id = callback["id"]
    data = callback.get("data", "")
    message = callback.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    action, separator, order_key = data.partition("|")

    try:
        telegram("answerCallbackQuery", {
            "callback_query_id": callback_id,
            "text": "Обрабатываю..."
        })
    except Exception as error:
        print(f"Не удалось закрыть индикатор кнопки: {error}")

    order = orders.get(order_key)
    if not chat_id or not order:
        if chat_id:
            send(chat_id, "Не нашёл данные этого заказа. Возможно, он уже обработан.")
        return

    if action == "reply":
        send(chat_id, "✍ Черновик отклика:\n\n" + make_reply(order))
    elif action == "skip":
        orders.pop(order_key, None)
        save_json(ORDERS_FILE, orders)
        send(chat_id, "Заказ пропущен.")


def check_updates(orders):
    offset = 0
    if OFFSET_FILE.exists():
        try:
            offset = int(OFFSET_FILE.read_text().strip())
        except Exception:
            offset = 0

    try:
        telegram("deleteWebhook", {"drop_pending_updates": "false"})
    except Exception:
        pass

    updates = telegram("getUpdates", {
        "offset": offset,
        "timeout": 0,
        "allowed_updates": json.dumps(["message", "callback_query"])
    })

    for update in updates:
        offset = max(offset, update["update_id"] + 1)

        if "callback_query" in update:
            handle_callback(update["callback_query"], orders)
            continue

        message = update.get("message")
        if not message:
            continue

        command = message.get("text", "").strip()
        chat_id = message["chat"]["id"]

        if command.startswith("/start"):
            send(chat_id, "🔎 Freelance Radar запущен!\n\n/id — узнать ID чата\n/status — проверить работу")
        elif command.startswith("/id"):
            send(chat_id, f"Твой Chat ID: {chat_id}")
        elif command.startswith("/status"):
            send(chat_id, "🟢 Freelance Radar работает. Проверка выполняется при запуске GitHub Actions.")

    OFFSET_FILE.write_text(str(offset))


def main():
    print("🚀 Freelance Radar запущен")
    orders = load_json(ORDERS_FILE, {})
    check_updates(orders)

    if not CHAT_ID:
        print("ОШИБКА: CHAT_ID не указан")
        return

    seen = load_seen()
    new_seen = set(seen)
    pending = []

    for channel in CHANNELS:
        print(f"Проверка @{channel}")
        try:
            posts = get_channel_posts(channel)
            print(f"Найдено публикаций: {len(posts)}")
            for post in posts:
                if post["id"] in seen:
                    continue
                if matches(post["text"]):
                    pending.append((channel, post))
                else:
                    new_seen.add(post["id"])
        except Exception as error:
            print(f"Ошибка @{channel}: {error}")

    sent_count = 0
    for channel, post in pending[:MAX_ALERTS_PER_RUN]:
        order_key = post["id"]
        orders[order_key] = {
            "channel": channel,
            "text": post["text"],
            "link": post["link"]
        }
        send_order_card(CHAT_ID, channel, post, order_key)
        new_seen.add(post["id"])
        sent_count += 1
        print(f"Отправлена карточка заказа из @{channel}")

    save_json(ORDERS_FILE, orders)
    save_seen(new_seen)
    print(f"Отправлено карточек: {sent_count}")
    print("✅ Проверка завершена")


if __name__ == "__main__":
    main()