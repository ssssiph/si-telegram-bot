from aiogram import Router, F
from aiogram.types import Message
from database import get_connection

router = Router()

@router.message(F.text == "👤 Аккаунт")
async def account_info(message: Message):
    conn = await get_connection()
    try:
        user = await conn.fetchrow("SELECT * FROM users WHERE tg_id = $1", message.from_user.id)
        if not user:
            await conn.execute("""
                INSERT INTO users (tg_id, username, full_name, rank, balance)
                VALUES ($1, $2, $3, 'Гость', 0)
            """, message.from_user.id, message.from_user.username or "-", message.from_user.full_name or "-")
            user = await conn.fetchrow("SELECT * FROM users WHERE tg_id = $1", message.from_user.id)

        await message.answer(
            f"<b>🧾 Ваш аккаунт:</b>\n"
            f"ID: <code>{user['tg_id']}</code>\n"
            f"Имя: {user['full_name']}\n"
            f"Юзернейм: {user['username']}\n"
            f"Ранг: {user['rank']}\n"
            f"💎 Баланс: {user['balance']}"
        )
    finally:
        await conn.close()
