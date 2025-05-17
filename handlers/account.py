from aiogram import Router, F
from aiogram.types import Message
from database import get_connection

router = Router()

@router.message(F.text == "👤 Аккаунт")
async def account_info(message: Message):
    async with await get_connection() as conn:
        user = await conn.fetchrow("SELECT * FROM users WHERE tg_id = $1", message.from_user.id)
        if not user:
            await message.answer("❗ Пользователь не найден.")
            return

        username = f"@{user['username']}" if user['username'] else "-"
        full_name = user['full_name'] or "-"
        rank = user['rank']
        balance = user['balance']

        await message.answer(
            f"<b>🧾 Ваш аккаунт:</b>\n"
            f"ID: <code>{user['tg_id']}</code>\n"
            f"Имя: {full_name}\n"
            f"Юзернейм: {username}\n"
            f"Ранг: {rank}\n"
            f"💎 Баланс: {balance}"
        )
