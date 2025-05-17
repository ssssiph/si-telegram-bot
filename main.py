import asyncio
import os
import asyncpg
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL").replace("postgresql://", "postgresql+asyncpg://")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

# 📥 Inline меню
menu_inline = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="👤 Аккаунт", callback_data="account")],
    [InlineKeyboardButton(text="🎯 События", callback_data="soon")],
    [InlineKeyboardButton(text="⚙ Настройки", callback_data="soon")],
    [InlineKeyboardButton(text="📩 Связь", callback_data="contact")],
    [InlineKeyboardButton(text="🛠 Управление", callback_data="manage")],
])

async def create_tables(conn):
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
        tg_id BIGINT PRIMARY KEY,
        username TEXT,
        rank TEXT DEFAULT 'Гость',
        balance INTEGER DEFAULT 0
    );
    """)
    user = await conn.fetchrow("SELECT * FROM users WHERE tg_id = 1016554091")
    if not user:
        await conn.execute("""
            INSERT INTO users (tg_id, username, rank, balance) 
            VALUES (1016554091, 'siph_director', 'Генеральный директор', 0)
        """)
    else:
        await conn.execute("UPDATE users SET rank = 'Генеральный директор' WHERE tg_id = 1016554091")

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
        reply_markup=menu_inline
    )

@dp.callback_query(F.data == "account")
async def account_handler(callback: CallbackQuery):
    async with asyncpg.create_pool(DATABASE_URL) as pool:
        async with pool.acquire() as conn:
            user = await conn.fetchrow("SELECT * FROM users WHERE tg_id = $1", callback.from_user.id)
            if not user:
                await conn.execute(
                    "INSERT INTO users (tg_id, username) VALUES ($1, $2)",
                    callback.from_user.id, callback.from_user.username or ''
                )
                await callback.answer("🆕 Вы зарегистрированы. Повторите действие.", show_alert=True)
                return

            if callback.from_user.username and user['username'] != callback.from_user.username:
                await conn.execute(
                    "UPDATE users SET username = $1 WHERE tg_id = $2",
                    callback.from_user.username, callback.from_user.id
                )

            username = f"@{user['username']}" if user['username'] else "-"
            await callback.message.edit_text(
                f"<b>🧾 Ваш аккаунт:</b>\n"
                f"ID: <code>{user['tg_id']}</code>\n"
                f"Имя: {callback.from_user.full_name}\n"
                f"Юзернейм: {username}\n"
                f"Ранг: {user['rank']}\n"
                f"💎 Баланс: {user['balance']}",
                reply_markup=menu_inline
            )

@dp.callback_query(F.data == "soon")
async def soon_handler(callback: CallbackQuery):
    await callback.answer("🚧 Скоро...", show_alert=True)

@dp.callback_query(F.data == "contact")
async def contact_handler(callback: CallbackQuery):
    async with asyncpg.create_pool(DATABASE_URL) as pool:
        async with pool.acquire() as conn:
            user = await conn.fetchrow("SELECT * FROM users WHERE tg_id = $1", callback.from_user.id)
            if user and user["rank"] in ("Стажёр", "Сотрудник", "Генеральный директор"):
                await callback.answer("📬 Связь скоро будет добавлена.", show_alert=True)
            else:
                await callback.answer("⛔ Доступ запрещён.", show_alert=True)

@dp.callback_query(F.data == "manage")
async def manage_handler(callback: CallbackQuery):
    async with asyncpg.create_pool(DATABASE_URL) as pool:
        async with pool.acquire() as conn:
            user = await conn.fetchrow("SELECT * FROM users WHERE tg_id = $1", callback.from_user.id)
            if user and user["rank"] == "Генеральный директор":
                await callback.answer("🛠 Панель управления скоро будет доступна.", show_alert=True)
            else:
                await callback.answer("⛔ Только для Генерального директора.", show_alert=True)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
