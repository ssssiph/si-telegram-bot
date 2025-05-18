from aiogram import Router, F
from aiogram.types import Message
from database import get_connection

router = Router()

@router.message(F.text.strip() == "👤 Аккаунт")
async def account_info(message: Message):
    conn = await get_connection()
    try:
        user = await conn.fetchrow("SELECT * FROM users WHERE tg_id = $1", message.from_user.id)
        if not user:
            await message.answer("❗ Пользователь не найден.")
            return

        username = f"@{user.get('username', '-')}" if user.get('username') else "-"
        full_name = message.from_user.full_name or "-"
        rank = user.get('rank', "Гость")
        balance = user.get('balance', 0)

        await message.answer(
            f"<b>🧾 Ваш аккаунт:</b>\n"
            f"ID: <code>{user['tg_id']}</code>\n"
            f"Имя: {full_name}\n"
            f"Юзернейм: {username}\n"
            f"Ранг: {rank}\n"
            f"💎 Баланс: {balance}"
        )
    finally:
        await conn.close()
