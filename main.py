import asyncio
import os
import asyncpg
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL").replace("postgresql://", "postgresql+asyncpg://")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

# 👇 Обычное клавиатурное меню (как раньше)
menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="👤 Аккаунт"), KeyboardButton(text="🎯 События")],
    [KeyboardButton(text="⚙ Настройки"), KeyboardButton(text="📩 Связь")],
    [KeyboardButton(text="🛠 Управление")]
], resize_keyboard=True)

async def create_tables(conn):
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
        tg_id BIGINT PRIMARY KEY,
        username TEXT,
        rank TEXT DEFAULT 'Гость',
        balance INTEGER DEFAULT 0
    );
    """)
    # Обновим или добавим Генерального директора
    user = await conn.fetchrow("SELECT * FROM users WHERE tg_id = 1016554091")
    if not user:
        await conn.execute("""
            INSERT INTO users (tg_id, username, rank, balance)
            VALUES (1016554091, 'siph_director', 'Генеральный директор', 0)
        """)
    else:
        await conn.execute("""
            UPDATE users SET rank = 'Генеральный директор' WHERE tg_id = 1016554091
        """)

async def get_or_create_user(conn, user):
    existing = await conn.fetchrow("SELECT * FROM users WHERE tg_id = $1", user.id)
    if not existing:
        await conn.execute(
            "INSERT INTO users (tg_id, username) VALUES ($1, $2)",
            user.id, user.username or ''
        )

@dp.message(F.text.in_({"/start", "начать"}))
async def start_handler(message: Message):
    async with asyncpg.create_pool(DATABASE_URL) as pool:
        async with pool.acquire() as conn:
            await create_tables(conn)
            await get_or_create_user(conn, message.from_user)
    await message.answer(
        f"Добро пожаловать, <b>{message.from_user.full_name}</b>!",
        reply_markup=menu
    )

# 👇 Остальной код оставляем как есть...

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
