
import asyncio
import os
import aiosqlite

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message

TOKEN = os.getenv("BOT_TOKEN")
DB = "radar.db"

bot = Bot(token=TOKEN)
dp = Dispatcher()


async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY
            )
        """)
        await db.commit()


async def add_user(user_id):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
            (user_id,)
        )
        await db.commit()


async def get_users():
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT user_id FROM users") as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


@dp.message(Command("start"))
async def start(message: Message):
    await add_user(message.from_user.id)

    await message.answer(
        "🔎 <b>Freelance Radar запущен!</b>\n\n"
        "Я буду присылать сюда новые заказы из подключённых "
        "Telegram-каналов.\n\n"
        "Команды:\n"
        "/start — запустить бота\n"
        "/status — проверить работу",
        parse_mode="HTML"
    )


@dp.message(Command("status"))
async def status(message: Message):
    await message.answer(
        "🟢 Бот работает и готов отслеживать новые публикации."
    )


@dp.channel_post()
async def channel_post(message: Message):
    text = message.text or message.caption or ""

    if not text:
        return

    keywords = [
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

    if not any(word in text.lower() for word in keywords):
        return

    channel = message.chat.username
    if channel:
        link = f"https://t.me/{channel}/{message.message_id}"
    else:
        link = ""

    notification = (
        "🚀 <b>Найдена новая заявка!</b>\n\n"
        f"{text[:3000]}\n\n"
        f'<a href="{link}">Открыть публикацию</a>'
        if link else
        "🚀 <b>Найдена новая заявка!</b>\n\n" + text[:3000]
    )

    for user_id in await get_users():
        try:
            await bot.send_message(
                user_id,
                notification,
                parse_mode="HTML"
            )
        except Exception:
            pass


async def main():
    if not TOKEN:
        raise RuntimeError("Не задан BOT_TOKEN")

    await init_db()
    print("Freelance Radar запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
